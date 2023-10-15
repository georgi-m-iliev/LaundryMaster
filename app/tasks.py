import os
import time
from flask import Flask
from celery import Celery, Task, shared_task

from app.models import User, WashingMachine
from app.functions import send_push_to_user, stop_cycle


def celery_init_app(app: Flask) -> Celery:
    class FlaskTask(Task):
        def __call__(self, *args: object, **kwargs: object) -> object:
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(app.config["CELERY"])
    celery_app.set_default()
    app.extensions["celery"] = celery_app
    return celery_app


@shared_task(ignore_result=False)
def watch_usage(user_id: int, terminate_cycle: bool):
    print("Starting task...")
    old_usage = WashingMachine.query.first().currentkwh
    while True:
        time.sleep(os.getenv("FLASK_CYCLE_CHECK_INTERVAL", 60))
        new_usage = WashingMachine.query.first().currentkwh
        if abs(new_usage - old_usage) < 0.0001:
            # Usage has not changed, cycle probably ended
            # Wait 3 minutes and check again to make sure
            time.sleep(os.getenv("FLASK_CYCLE_CHECK_INTERVAL", 60) * 3)
            new_usage = WashingMachine.query.first().currentkwh
            if abs(new_usage - old_usage) < 0.0001:
                # Cycle has ended for sure
                break
        old_usage = new_usage

    # Cycle has ended, send push notification
    send_push_to_user(user_id, "Your cycle has ended!", "Go pick you laundry!")

    if terminate_cycle:
        # Terminate cycle
        stop_cycle(User.query.get(user_id))

    print("Ending task....")
