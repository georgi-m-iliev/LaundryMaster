import os
import time
import logging
import datetime

from flask import Flask
from celery import Celery, Task, shared_task, current_app, current_task
from celery.schedules import crontab

from app.db import db
from app.models import User, WashingMachine, Notification, CeleryTask
from app.models import (schedule_reminder_notification, cycle_paused_notification, cycle_ended_notification,
                        cycle_termination_reminder_notification)
from app.functions import (send_push_to_user, stop_cycle, update_energy_consumption, get_realtime_current_usage,
                           trigger_relay, recalculate_cycles_cost)
from app.candy import CandyWashingMachine, CandyMachineState, fetch_appliance_data


def celery_init_app(app: Flask) -> Celery:
    class FlaskTask(Task):
        def __call__(self, *args: object, **kwargs: object) -> object:
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(app.config["CELERY"])
    celery_app.set_default()
    celery_app.conf.update(
        task_track_started=True,
        worker_log_format='%(asctime)s %(levelname)-8s %(message)s',
        worker_task_log_format='%(asctime)s %(levelname)-8s - Task %(task_id)s - %(message)s',
        worker_log_file='latest.log'  # Use the same log file as Flask
    )
    celery_app.logger = logging.getLogger(__name__)

    app.extensions["celery"] = celery_app

    celery_app.conf.beat_schedule = {
        "Send notification to debtors every two days": {
            "task": "send_notification_to_debtors",
            "schedule": crontab(minute="0", hour="16", day_of_week="*/2")
        }
    }

    return celery_app


@shared_task(ignore_result=False)
def cycle_end_notification_task_old(user_id: int, terminate_cycle: bool):
    """ Legacy task for notification of cycle end. Watches the energy consumption and decides based on usage. """
    def wait_usage_over_threshold():
        current_app.logger.info('Watching energy consumption and waiting it to get over threshold...')
        while True:
            usage = get_realtime_current_usage()
            if usage > int(os.getenv('WASHING_MACHINE_WATT_THRESHOLD')):
                break
            time.sleep(int(os.getenv("CYCLE_CHECK_INTERVAL", 60)) / 2)
        current_app.logger.info('Usage is over threshold!')

    def watch_usage():
        current_app.logger.info('Watching energy consumption and waiting it to get under threshold...')
        counter = 0
        while True:
            usage = get_realtime_current_usage()
            if usage < int(os.getenv('WASHING_MACHINE_WATT_THRESHOLD')):
                # Usage is under threshold, start cycle end detection
                while counter < 10:
                    current_app.logger.info('Usage under threshold, checking if it stays under...')
                    usage = get_realtime_current_usage()
                    if usage > int(os.getenv('WASHING_MACHINE_WATT_THRESHOLD')):
                        # Usage has gone over threshold, cycle hasn't ended
                        current_app.logger.info('Usage went over threshold, cycle has not ended yet.')
                        counter = 0
                        break
                    counter += 1
                    time.sleep(int(os.getenv("CYCLE_CHECK_INTERVAL", 60)) / 2)
                if counter == 10:
                    # Usage has been under threshold for 5 minutes and hadn't gone over, cycle has probably ended
                    break
            time.sleep(int(os.getenv("CYCLE_CHECK_INTERVAL", 60)))

        current_app.logger.info('Usage is under threshold for enough time and cycle should be completed!')

        # Cycle has ended, send push notification
        send_push_to_user(
            user=user,
            notification=cycle_ended_notification
        )

    print("Starting task...")
    # Give a time window of 10 minutes to start a washing cycle
    time.sleep(10 * 60)
    current_app.logger.info("Grace period for starting the program ended.")

    # When using celery we must provide the bare minimum of required data,
    # so we fetch the user by the id provided
    user = User.query.filter_by(id=user_id).first()

    # Wait until usage is over threshold
    wait_usage_over_threshold()

    # Usage is over threshold, monitor it until it falls under threshold
    watch_usage()

    if terminate_cycle:
        # Terminate cycle if enabled in settings
        stop_cycle(user)
        print("Sending reminder to user...")
        send_push_to_user(
            user=user,
            notification=cycle_termination_reminder_notification
        )
    else:
        # Otherwise, remind the user that the cycle must be terminated if the washing has ended!
        current_app.logger.info("User doesn't want automatic cycle termination, reminding them to terminate it.")
        i = 0
        while i < 10:
            time.sleep(5 * 60)
            if get_realtime_current_usage() > int(os.getenv('WASHING_MACHINE_WATT_THRESHOLD')):
                # Usage is over threshold again, start detection all over again
                current_app.logger.warning('Usage went over threshold again, starting detection all over again.')
                watch_usage()
                i = 0
                continue

            print("Sending reminder to user...")
            send_push_to_user(
                user=user,
                notification=cycle_termination_reminder_notification
            )
            i += 1

    print("Ending task....")


@shared_task(ignore_result=True)
def release_door(user_username: str):
    """ Task to release the door of the washing machine. """
    current_app.logger.info(f"Starting task to release the door for {user_username}...")

    current_app.logger.info("Sending request to turn on the relay through Shelly Cloud API...")
    counter = 0
    while trigger_relay('on') != 200:
        current_app.logger.error("Request to turn on the relay through Shelly Cloud API FAILED! Retrying...")
        if counter == 10:
            current_app.logger.warning("Tried to turn on the relay 10 times. Failed :(")
            return
        time.sleep(2)
        counter += 1

    current_app.logger.info("Washing machine should be on. Waiting some time...")
    time.sleep(30)

    current_app.logger.info("Sending request to turn off the relay through Shelly Cloud API...")
    counter = 0
    while trigger_relay('off') != 200:
        current_app.logger.error("Request to turn off the relay through Shelly Cloud API FAILED! Trying again...")
        if counter == 10:
            current_app.logger.warning("Tried to turn off the relay 10 times. Failed :(")
            return
        time.sleep(2)
        counter += 1

    current_app.logger.info("Task to release the door ended.")
    CeleryTask.query.filter_by(id=current_task.request.id).delete()


@shared_task(ignore_result=True)
def schedule_notification(user_id: int):
    """ Task to send a push notification to the user about their scheduled washing. """
    user = User.query.filter_by(id=user_id).first()
    if user:
        current_app.logger.info(f'Reminding {user.username} about their scheduled washing...')
        result = send_push_to_user(user=user, notification=schedule_reminder_notification)
        if False in result:
            current_app.logger.warning(f'Sending push notification failed for some subscriptions: {result}')
    else:
        current_app.logger.warning(f'User with id {user_id} not found!')


@shared_task(ignore_result=False)
def cycle_end_notification_task(user_id: int, terminate_cycle: bool):
    """ Task to send a push notification to the user about the end of their washing cycle."""
    current_app.logger.info("Starting task...")
    user = User.query.filter_by(id=user_id).first()
    # Give a time window of 10 minutes to start a washing cycle
    time.sleep(10 * 60)
    current_app.logger.info("Grace period for starting the program ended.")

    washing_machine = CandyWashingMachine.get_instance()
    while (washing_machine.machine_state != CandyMachineState.FINISHED1 and
           washing_machine.machine_state != CandyMachineState.FINISHED2):

        if washing_machine.machine_state == CandyMachineState.PAUSED:
            current_app.logger.info("Machine is paused, notifying user...")
            send_push_to_user(
                user=user,
                notification=cycle_paused_notification
            )
            time.sleep(60)
        elif washing_machine.machine_state == CandyMachineState.IDLE:
            current_app.logger.info("Machine is idle, waiting for it to start...")
            time.sleep(60)
        elif washing_machine.machine_state == CandyMachineState.RUNNING:
            current_app.logger.info("Machine is running, waiting for it to finish...")
            time.sleep(5 * 60)
        else:
            current_app.logger.warning(f"Non-captured state: {washing_machine.machine_state.code} - {washing_machine.machine_state.label}")
            time.sleep(60)
        washing_machine.update()

    current_app.logger.info("Washing cycle has ended!")
    if terminate_cycle:
        # Terminate cycle if enabled in settings
        current_app.logger.info("Automatic termination of cycle...")
        stop_cycle(user)
    else:
        # Otherwise, remind the user that the cycle must be terminated if the washing has ended!
        current_app.logger.info("User doesn't want automatic cycle termination, reminding them to terminate it.")
        send_push_to_user(
            user=user,
            notification=cycle_ended_notification
        )

        time.sleep(10 * 60)
        current_app.logger.info("User was notified but didn't terminate the cycle, reminding them...")
        for _ in range(10):
            current_app.logger.info("Sending reminder to user...")
            send_push_to_user(
                user=user,
                notification=cycle_termination_reminder_notification
            )
            time.sleep(5 * 60)

    current_app.logger.info("Ending task....")
    CeleryTask.query.filter_by(id=current_task.request.id).delete()


@shared_task()
def recalculate_cycles_cost_task():
    """ Task to recalculate the cost of cycles. """
    current_app.logger.info("Task to recalculate cycles will start in 30 minutes...")
    # Giving some time to cancel the task if it was started by mistake
    time.sleep(30 * 60)

    current_app.logger.info(f"Starting task to recalculate cycles cost at {datetime.datetime.now} ...")
    recalculate_cycles_cost()
    current_app.logger.info(f"Task to recalculate cycles cost ended at {datetime.datetime.now}.")
    CeleryTask.query.filter_by(id=current_task.request.id).delete()


@shared_task(name='send_notification_to_debtors', ignore_result=True)
def send_notification_to_debtors():
    from app.functions import notify_debtors
    current_app.logger.info("Will send notifications to all debtors...")
    notify_debtors()
    current_app.logger.info("All debtors were notified. Exiting...")