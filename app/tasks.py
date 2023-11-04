import os
import time
from flask import Flask
from celery import Celery, Task, shared_task
from celery.schedules import crontab

from app.models import User, WashingMachine
from app.functions import send_push_to_user, stop_cycle, update_energy_consumption, get_realtime_energy_consumption


def celery_init_app(app: Flask) -> Celery:
    class FlaskTask(Task):
        def __call__(self, *args: object, **kwargs: object) -> object:
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(app.config["CELERY"])
    celery_app.set_default()
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
def watch_usage(user_id: int, terminate_cycle: bool):
    print("Starting task...")
    # Give a time window of 10 minutes to start a washing cycle
    time.sleep(10 * 60)
    counter = 0
    while True:
        usage = get_realtime_energy_consumption()
        if usage < int(os.getenv('WASHING_MACHINE_WATT_THRESHOLD')):
            # Usage is under threshold, start cycle end detection
            while True:
                usage = get_realtime_energy_consumption()
                if usage > int(os.getenv('WASHING_MACHINE_WATT_THRESHOLD')):
                    # Usage has gone over threshold, cycle hasn't ended
                    counter = 0
                    break
                if counter == 10:
                    # Usage has been under threshold for 5 minutes Cycle has ended
                    break
                counter += 1
                time.sleep(os.getenv("CYCLE_CHECK_INTERVAL", 60) / 2)
        if counter == 10:
            # Cycle has ended
            break
        time.sleep(os.getenv("CYCLE_CHECK_INTERVAL", 60))

    # Cycle has ended, send push notification
    send_push_to_user(user_id, "Your cycle has ended!", "Go pick you laundry!")

    if terminate_cycle:
        # Terminate cycle if enabled in settings
        stop_cycle(User.query.get(user_id))

    print("Ending task....")


@shared_task(name="update_usage")
def update_usage():
    update_energy_consumption()
