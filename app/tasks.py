import os
import time
import logging

from flask import Flask
from celery import Celery, Task, shared_task, current_app
from celery.schedules import crontab

from app.models import User, WashingMachine
from app.functions import send_push_to_user, stop_cycle, update_energy_consumption, get_realtime_current_usage, trigger_relay


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
    app.config['CELERYBEAT_SCHEDULE'] = {
        # Executes every minute
        'update_usage_task': {
            'task': 'update_usage',
            'schedule': crontab(minute="*")
        }
    }
    return celery_app


@shared_task(ignore_result=False)
def watch_usage_and_notify_cycle_end(user_id: int, terminate_cycle: bool):
    def wait_usage_over_threshold():
        while True:
            usage = get_realtime_current_usage()
            if usage > int(os.getenv('WASHING_MACHINE_WATT_THRESHOLD')):
                break
            time.sleep(int(os.getenv("CYCLE_CHECK_INTERVAL", 60)) / 2)

    def watch_usage():
        counter = 0
        while True:
            usage = get_realtime_current_usage()
            if usage < int(os.getenv('WASHING_MACHINE_WATT_THRESHOLD')):
                # Usage is under threshold, start cycle end detection
                while counter < 10:
                    usage = get_realtime_current_usage()
                    if usage > int(os.getenv('WASHING_MACHINE_WATT_THRESHOLD')):
                        # Usage has gone over threshold, cycle hasn't ended
                        counter = 0
                        break
                    counter += 1
                    time.sleep(int(os.getenv("CYCLE_CHECK_INTERVAL", 60)) / 2)
            if counter == 20:
                # Usage has been under threshold for 10 minutes, cycle has probably ended
                break
            time.sleep(int(os.getenv("CYCLE_CHECK_INTERVAL", 60)))

        # Cycle has ended, send push notification
        send_push_to_user(
            user,
            "Your cycle has ended!",
            "Go pick your laundry!",
            icon="cycle-done-icon.png"
        )

    print("Starting task...")
    # Give a time window of 10 minutes to start a washing cycle
    time.sleep(10 * 60)

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
    else:
        # Allowing a time window of 10 minutes to go pick up the laundry
        print("Waiting 10 minutes before reminding user to pick up laundry...")
        # time.sleep(10 * 60)

        # Otherwise, remind the user that the cycle must be terminated if the washing has ended!
        i = 0
        while i < 10:
            time.sleep(5 * 60)
            if get_realtime_current_usage() > int(os.getenv('WASHING_MACHINE_WATT_THRESHOLD')):
                # Usage is over threshold again, start detection all over again
                watch_usage()
                i = 0
                continue

            print("Sending reminder to user...")
            send_push_to_user(
                user,
                "Your cycle is still running...",
                "Did you forget to terminate it?",
                icon="reminder-icon.png"
            )
            i += 1

    print("Ending task....")


@shared_task(name="update_energy_consumption")
def update_energy_consumption_task():
    update_energy_consumption()


@shared_task(ignore_result=True)
def release_door(user_username: str):
    current_app.logger.info(f"Starting task to release the door for {user_username}...")

    current_app.logger.info("Sending request to turn on the relay through Shelly Cloud API...")
    if trigger_relay('on') != 200:
        current_app.logger.error("Request to turn off the relay through Shelly Cloud API FAILED!")
        return
    current_app.logger.info("Washing machine should be on. Waiting some time...")
    time.sleep(30)

    current_app.logger.info("Sending request to turn off the relay through Shelly Cloud API...")
    if trigger_relay('off') != 200:
        current_app.logger.error("Request to turn off the relay through Shelly Cloud API FAILED!")

    current_app.logger.info("Task to release the door ended.")
