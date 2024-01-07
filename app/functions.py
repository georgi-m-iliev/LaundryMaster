import os, decimal, datetime, json, math, requests
from requests.exceptions import RequestException

from flask import session, current_app, flash
from celery.result import AsyncResult
from pywebpush import webpush, WebPushException
from sqlalchemy import or_, and_

from app.db import db
from app.models import User, WashingCycle, WashingMachine, PushSubscription, split_cycles


def start_cycle(user: User):
    if WashingCycle.query.filter_by(endkwh=None, end_timestamp=None).all():
        # User has an already running cycle
        current_app.logger.error(f"User {user.username} tried to start a cycle, but one was already active.")
        flash(message='You already have a cycle running!', category='toast-warning')
        raise ChildProcessError('User already has a cycle running!')

    # No cycle running, create new cycle
    current_app.logger.info(f'User {user.username} is starting a new cycle.')

    if trigger_relay('on') != 200:
        current_app.logger.error("Request to turn on the relay through Shelly Cloud API FAILED!")
        flash('Request to turn on the relay failed!\nPlease try again!', category='toast-error')
        raise ChildProcessError('Request to turn on the relay failed!')

    try:
        update_energy_consumption()
        new_cycle = WashingCycle(user_id=user.id, startkwh=WashingMachine.query.first().currentkwh)
        db.session.add(new_cycle)
        db.session.commit()
        current_app.logger.info(f'User {user.username} successfully started a new cycle.')
        flash('Cycle successfully started!', category='toast-success')
    except RequestException:
        current_app.logger.error(f'Error with initialising a cycle for user {user.username}.')
        flash('Unexpected error occurred!\nPlease try again!', category='toast-error')
        raise ChildProcessError('Error with initialising a cycle for user {user.username}.')


def stop_cycle(user: User):
    cycle: WashingCycle = WashingCycle.query.filter_by(user_id=user.id, end_timestamp=None).first()
    if cycle:
        # Cycle belonging to current user was found, stopping it
        current_app.logger.info(f'User {user.username} is stopping their cycle.')

        if trigger_relay('off') != 200:
            current_app.logger.error("Request to turn off the relay through Shelly Cloud API FAILED!")
            flash('Request to turn off the relay failed!\nPlease try again!', category='toast-error')
            return

        try:
            update_energy_consumption()
            cycle.endkwh = WashingMachine.query.first().currentkwh
            cycle.end_timestamp = db.func.current_timestamp()
            cycle.cost = (cycle.endkwh - cycle.startkwh) * WashingMachine.query.first().costperkwh
            if cycle.cost == 0:
                db.session.delete(cycle)

            if notification_task_id := WashingMachine.query.first().notification_task_id:
                AsyncResult(notification_task_id).revoke(terminate=True)
                WashingMachine.query.first().notification_task_id = None

            db.session.commit()
            current_app.logger.info(f'User {user.username} successfully stopped their cycle.')
            flash('Cycle successfully terminated!', category='toast-success')
        except RequestException:
            current_app.logger.error(
                f'Error with terminating a cycle for user {user.username} due to failure of energy consumption update.')
            flash('Unexpected error occurred!\nPlease try again!', category='toast-error')
        except Exception as e:
            current_app.logger.error(f'Error with terminating a cycle for user {user.username}. {e.__str__()}')
            flash('Unexpected error occurred!\nPlease try again!', category='toast-error')
    else:
        current_app.logger.error(f"User {user.username} tried to stop a cycle, but they didn't start one.")
        flash('You do not have a running cycle!', category='toast-warning')


def update_cycle(user: User):
    cycle = WashingCycle.query.filter_by(end_timestamp=None).join(User).filter(WashingCycle.user_id == User.id).first()
    if cycle:
        if cycle.user_id == user.id:
            return {'state': 'running', 'id': cycle.id}
        else:
            return {'state': 'unavailable', 'id': None, 'user': cycle.user.first_name}
    else:
        return {'state': 'available', 'id': None}


def calculate_charges(user: User):
    """Calculate the monthly charges for a user."""
    charges: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_not(None),
        or_(
            WashingCycle.user_id == user.id,
            WashingCycle.split_users.any(id=user.id)
        ),
        db.func.extract('month', WashingCycle.end_timestamp) == datetime.datetime.now().month
    ).all()

    result = 0
    for charge in charges:
        result += charge.cost

    return result


def calculate_usage(user: User):
    """Calculate the monthly usage of electricity for a user."""
    usage: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_not(None),
        or_(
            WashingCycle.user_id == user.id,
            WashingCycle.split_users.any(id=user.id)
        ),
        db.func.extract('month', WashingCycle.end_timestamp) == datetime.datetime.now().month
    ).all()

    result = 0
    for use in usage:
        result += use.endkwh - use.startkwh

    return result


def calculate_unpaid_cycles_cost(user: User = None):
    """Calculate the unpaid cycles for a user or at all."""
    if user is None:
        unpaid: list[WashingCycle] = WashingCycle.query.filter(
            WashingCycle.end_timestamp.is_not(None),
            WashingCycle.paid.is_(False)
        ).all()
    else:
        unpaid: list[WashingCycle] = WashingCycle.query.filter(
            WashingCycle.end_timestamp.is_not(None),
            or_(
                and_(
                    WashingCycle.user_id == user.id,
                    WashingCycle.paid.is_(False),
                ),
                WashingCycle.split_users.any(id=user.id)
            )
        ).all()

        paid_split_cycles_ids = [cycle.cycle_id for cycle in db.session.query(split_cycles).filter_by(
            user_id=user.id, paid=True
        ).all()]
        unpaid = [cycle for cycle in unpaid if cycle.id not in paid_split_cycles_ids]

    result = 0
    for unpaid_cycle in unpaid:
        if hasattr(unpaid_cycle, 'split_cost'):
            result += unpaid_cycle.split_cost
        else:
            result += unpaid_cycle.cost

    return result


def calculate_savings(user: User):
    """Calculate the savings from having personal washing machine."""
    cycles: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_not(None),
        or_(
            WashingCycle.user_id == user.id,
            WashingCycle.split_users.any(id=user.id)
        ),
        WashingCycle.cost > 0.30,  # minimum cost of washing and drying, so the calculation would be accurate
        db.func.extract('month', WashingCycle.end_timestamp) == datetime.datetime.now().month
    ).all()

    public_wash_cost = WashingMachine.query.first().public_wash_cost

    result = 0
    for cycle in cycles:
        result += public_wash_cost - cycle.cost

    return result


def get_running_time() -> str:
    """Calculate the running time of the current cycle."""
    cycle: WashingCycle = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_(None)
    ).first()
    if cycle is not None:
        return str(datetime.datetime.now(datetime.timezone.utc) - cycle.start_timestamp).split('.')[0].zfill(8)
    else:
        return '00:00:00'


def calculate_monthly_statistics(user: User, months: int = 6) -> dict:
    """Calculate the monthly statistics for a user."""
    if months <= 0:
        return {"labels": [], "data": [0, 0, 0, 0, 0, 0]}

    stat_labels: list[str] = []
    stat_data: list[str] = []
    year: int = datetime.datetime.now().year
    month: int = datetime.datetime.now().month

    for i in range(months):
        # print("Month " + str(month) + " Year " + str(year))
        cycles = WashingCycle.query.filter(
            WashingCycle.end_timestamp.is_not(None),
            or_(
                WashingCycle.user_id == user.id,
                WashingCycle.split_users.any(id=user.id)
            ),
            db.func.extract('month', WashingCycle.end_timestamp) == month,
            db.func.extract('year', WashingCycle.end_timestamp) == year,
        ).all()

        total_cost = 0

        for cycle in cycles:
            total_cost += cycle.cost

        stat_labels.append(datetime.date(year=year, month=month, day=1).strftime("%B")[0:3])
        stat_data.append(str(total_cost))

        if month == 1:
            month = 12
            year -= 1
        else:
            month -= 1
    stat_labels.reverse()
    stat_data.reverse()
    return {"labels": stat_labels, "data": stat_data}


def get_unpaid_list(user: User):
    """Get the unpaid cycles for a user."""
    cycles: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_not(None),
        or_(
            and_(
                WashingCycle.user_id == user.id,
                WashingCycle.paid.is_(False),
            ),
            WashingCycle.split_users.any(id=user.id)
        )
    ).order_by(WashingCycle.start_timestamp.desc(), WashingCycle.end_timestamp.desc()).all()

    paid_split_cycles_ids = [cycle.cycle_id for cycle in db.session.query(split_cycles).filter_by(user_id=user.id, paid=True).all()]
    cycles = [cycle for cycle in cycles if cycle.id not in paid_split_cycles_ids]

    for cycle in cycles:
        if split_users_count := len(cycle.split_users):
            cycle.split_cost = round(cycle.cost / (split_users_count + 1), 2)
            if cycle.split_cost * (split_users_count + 1) < cycle.cost:
                cycle.split_cost = round(cycle.split_cost + decimal.Decimal(0.01), 2)
            cycle.split_paid = False
        cycle.start_timestamp_formatted = cycle.start_timestamp.strftime("%d-%m-%Y %H:%M:%S")
        cycle.end_timestamp_formatted = cycle.end_timestamp.strftime("%d-%m-%Y %H:%M:%S")
    return cycles


def get_usage_list(user: User, limit: int = 10):
    """Get the usage list for a user."""
    cycles: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_not(None),
        or_(
            WashingCycle.user_id == user.id,
            WashingCycle.split_users.any(id=user.id)
        )
    ).order_by(WashingCycle.start_timestamp.desc(), WashingCycle.end_timestamp.desc()).limit(limit).all()

    for cycle in cycles:
        cycle.usedkwh = round(cycle.endkwh - cycle.startkwh, 2)
        if split_users_count := len(cycle.split_users):
            cycle.split_cost = round(cycle.cost / (split_users_count + 1), 2)
            if cycle.split_cost * (split_users_count + 1) < cycle.cost:
                cycle.split_cost = round(cycle.split_cost + decimal.Decimal(0.01), 2)
            if cycle.user_id != user.id:
                cycle.split_paid = db.session.query(split_cycles).filter_by(
                    cycle_id=cycle.id, user_id=user.id
                ).first().paid
        cycle.start_timestamp_formatted = cycle.start_timestamp.strftime("%d-%m-%Y %H:%M:%S")
        cycle.end_timestamp_formatted = cycle.end_timestamp.strftime("%d-%m-%Y %H:%M:%S")
        cycle.duration = str(cycle.end_timestamp - cycle.start_timestamp).split('.')[0]
    return cycles


def trigger_push_notification(push_subscription, title, body, icon=None, user=None):
    try:
        if user:
            current_app.logger.info(f'Sending push notification to {user.username}.')
        else:
            current_app.logger.info('Sending push notification to all users.')
        response = webpush(
            subscription_info=json.loads(push_subscription.subscription_json),
            data=json.dumps({"title": title, "body": body, "icon": icon}),
            vapid_private_key=current_app.config["PUSH_PRIVATE_KEY"],
            vapid_claims={"sub": "mailto:{}".format(current_app.config["PUSH_CLAIM_EMAIL"])}
        )
        return response.ok
    except WebPushException as ex:
        current_app.logger.error(f'Error trying to send notification to {user.username}.')
        if ex.response and ex.response.json():
            extra = ex.response.json()
            current_app.logger.error("Remote service replied with a {}:{}, {}", extra.code, extra.errno, extra.message)
        return False


def send_push_to_all(title, body):
    subscriptions = PushSubscription.query.all()
    return [trigger_push_notification(subscription, title, body) for subscription in subscriptions]


def send_push_to_user(user: User, title, body, icon=None):
    subscriptions = PushSubscription.query.filter_by(user_id=user.id).all()
    return [trigger_push_notification(subscription, title, body, icon=icon, user=user) for subscription in subscriptions]


def trigger_relay(mode: str):
    """Enable the relay on the Shelly device."""
    current_app.logger.info(f'Triggering relay through Shelly API to be {mode}.')
    response = requests.post(
        url='{}/device/relay/control'.format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
        data={
            'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
            'id': os.getenv('SHELLY_DEVICE_ID'),
            'channel': '0',
            'turn': 'on' if mode == 'on' else 'off'
        })
    return response.status_code


def get_energy_consumption():
    """ Queries Shelly Cloud API for energy consumption data in Watt-minute and return in kWatt-hour."""
    data = requests.post(
        url="{}/device/status".format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
        params={
            'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
            'id': os.getenv('SHELLY_DEVICE_ID')
        }
    )

    if data.status_code != 200:
        current_app.logger.error('Failed to get power consumption data from Shelly Cloud API')
        raise RequestException('Failed to get power consumption data from Shelly Cloud API')

    return data.json()['data']['device_status']['meters'][0]['total'] / 60000


def get_realtime_current_usage():
    """ Queries Shelly Cloud API for current usage data in Watt."""
    data = requests.post(
        url="{}/device/status".format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
        params={
            'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
            'id': os.getenv('SHELLY_DEVICE_ID')
        }
    )

    if data.status_code != 200:
        current_app.logger.error('Failed to get current usage data from Shelly Cloud API')
        raise RequestException('Failed to get current usage data from Shelly Cloud API')

    return data.json()['data']['device_status']['meters'][0]['power']


def update_energy_consumption():
    """ Updates the energy consumption in the database """
    washing_machine = WashingMachine.query.first()
    washing_machine.currentkwh = get_energy_consumption()
    db.session.commit()


def get_relay_temperature():
    data = requests.post(
        url="{}/device/status".format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
        params={
            'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
            'id': os.getenv('SHELLY_DEVICE_ID')
        }
    )

    if data.status_code != 200:
        raise RequestException('Failed to get data from Shelly Cloud API')

    return data.json()['data']['device_status']['temperature']


def get_relay_wifi_rssi():
    data = requests.post(
        url="{}/device/status".format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
        params={
            'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
            'id': os.getenv('SHELLY_DEVICE_ID')
        }
    )

    if data.status_code != 200:
        raise RequestException('Failed to get data from Shelly Cloud API')

    return data.json()['data']['device_status']['wifi_sta']['rssi']


def get_washer_info(shelly=True):
    """ Returns a dict with washing machine information """
    if shelly:
        shelly_request = requests.post(
            url="{}/device/status".format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
            params={
                'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
                'id': os.getenv('SHELLY_DEVICE_ID')
            }
        )

        if shelly_request.status_code != 200:
            current_app.logger.error('Failed to get current usage data from Shelly Cloud API')
            raise RequestException('Failed to get current usage data from Shelly Cloud API')

        shelly_data = shelly_request.json()

        return {
            "running_time": get_running_time(),
            "current_usage": shelly_data['data']['device_status']['meters'][0]['power'],
            "relay_temperature": shelly_data['data']['device_status']['temperature'],
            "relay_wifi_rssi": shelly_data['data']['device_status']['wifi_sta']['rssi']
        }

    return {"running_time": get_running_time()}
