import os, decimal, datetime, json, math, requests

from flask import session, current_app
from pywebpush import webpush, WebPushException

from app.db import db
from app.models import User, WashingCycle, WashingMachine, PushSubscription


def start_cycle(user: User):
    if WashingCycle.query.filter_by(endkwh=None, end_timestamp=None).all():
        # TODO: Cycle already running, display error
        pass
    else:
        # No cycle running, create new cycle
        if trigger_relay('on') != 200:
            # TODO: Handle error
            raise Exception('Failed to trigger relay on Shelly Cloud API')
        update_energy_consumption()
        new_cycle = WashingCycle(user_id=user.id, startkwh=WashingMachine.query.first().currentkwh)
        db.session.add(new_cycle)
        db.session.commit()


def stop_cycle(user: User):
    cycle: WashingCycle = WashingCycle.query.filter_by(user_id=user.id, end_timestamp=None).first()
    if cycle:
        # Cycle belonging to current user was found, stopping it
        if trigger_relay('off') != 200:
            # TODO: Handle error
            raise Exception('Failed to trigger relay on Shelly Cloud API')
        update_energy_consumption()
        cycle.endkwh = WashingMachine.query.first().currentkwh
        cycle.end_timestamp = db.func.current_timestamp()
        cycle.cost = (cycle.endkwh - cycle.startkwh) * WashingMachine.query.first().costperkwh
        db.session.commit()
    else:
        # TODO: No cycle belonging to current user was found, display error
        pass


def update_cycle(user: User):
    cycle = WashingCycle.query.filter_by(end_timestamp=None).first()
    if cycle:
        if cycle.user_id == user.id:
            # Current user owns the cycle
            # session['cycle_state'] = 'running'
            # session['cycle_id'] = cycle.id
            return {'state': 'running', 'id': cycle.id}
        else:
            # Current user does not own the cycle
            # session['cycle_state'] = 'unavailable'
            return {'state': 'unavailable', 'id': None}
    else:
        # session['cycle_state'] = 'available'
        return {'state': 'available', 'id': None}


def calculate_charges(user: User) -> decimal:
    """Calculate the monthly charges for a user."""
    charges: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.user_id == user.id,
        WashingCycle.end_timestamp.is_not(None),
        db.func.extract('month', WashingCycle.end_timestamp) == datetime.datetime.now().month
    ).all()

    result: decimal = 0
    for charge in charges:
        result += charge.cost

    return result


def calculate_usage(user: User) -> decimal:
    """Calculate the monthly usage of electricity for a user."""
    usage: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.user_id == user.id,
        WashingCycle.end_timestamp.is_not(None),
        db.func.extract('month', WashingCycle.end_timestamp) == datetime.datetime.now().month
    ).all()

    result: decimal = 0
    for use in usage:
        result += use.endkwh - use.startkwh

    return result


def calculate_unpaid_cycles_cost(user: User) -> decimal:
    """Calculate the unpaid cycles for a user."""
    unpaid: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.user_id == user.id,
        WashingCycle.end_timestamp.is_not(None),
        WashingCycle.paid.is_(False),
    ).all()

    result: decimal = 0
    for unpaid_cycle in unpaid:
        result += unpaid_cycle.cost

    return result


def calculate_savings(user: User) -> decimal:
    """Calculate the savings from having personal washing machine."""
    cycles: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.user_id == user.id,
        WashingCycle.end_timestamp.is_not(None),
        WashingCycle.cost > 0.20,
        db.func.extract('month', WashingCycle.end_timestamp) == datetime.datetime.now().month
    ).all()

    public_wash_cost = WashingMachine.query.first().public_wash_cost

    result: decimal = 0
    for cycle in cycles:
        result += public_wash_cost - cycle.cost

    return result


def calculate_running_time() -> str:
    """Calculate the running time of the current cycle."""
    cycle: WashingCycle = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_(None)
    ).first()
    if cycle is not None:
        return str(datetime.datetime.now(datetime.timezone.utc) - cycle.start_timestamp).split('.')[0].zfill(8)
    else:
        return "None"


def calculate_monthly_statistics(user: User, months: int = 6) -> dict:
    """Calculate the monthly statistics for a user."""
    if months > 0:
        stat_labels: list[str] = []
        stat_data: list[str] = []
        year: int = datetime.datetime.now().year
        month: int = datetime.datetime.now().month

        for i in range(months):
            # print("Month " + str(month) + " Year " + str(year))
            cycles = WashingCycle.query.filter(
                WashingCycle.user_id == user.id,
                WashingCycle.end_timestamp.is_not(None),
                db.func.extract('month', WashingCycle.end_timestamp) == month,
                db.func.extract('year', WashingCycle.end_timestamp) == year,
            ).all()

            total_cost: decimal = 0

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
    return {"labels": [], "data": [0, 0, 0, 0, 0, 0]}


def get_unpaid_list(user: User) -> list[WashingCycle]:
    """Get the unpaid cycles for a user."""
    cycles: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_not(None),
        WashingCycle.user_id == user.id,
        WashingCycle.paid.is_(False)
    ).order_by(WashingCycle.start_timestamp.desc(), WashingCycle.end_timestamp.desc()).all()

    # result = list()
    for cycle in cycles:
        cycle.start_timestamp_formatted = cycle.start_timestamp.strftime("%d-%m-%Y %H:%M:%S")
        cycle.end_timestamp_formatted = cycle.end_timestamp.strftime("%d-%m-%Y %H:%M:%S")
    return cycles


def get_usage_list(user: User, limit: int = 10) -> list[WashingCycle]:
    """Get the usage list for a user."""
    cycles: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_not(None),
        WashingCycle.user_id == user.id
    ).order_by(WashingCycle.start_timestamp.desc(), WashingCycle.end_timestamp.desc()).limit(limit).all()

    for cycle in cycles:
        cycle.usedkwh = round(cycle.endkwh - cycle.startkwh, 2)
        cycle.start_timestamp_formatted = cycle.start_timestamp.strftime("%d-%m-%Y %H:%M:%S")
        cycle.end_timestamp_formatted = cycle.end_timestamp.strftime("%d-%m-%Y %H:%M:%S")
        cycle.duration = str(cycle.end_timestamp - cycle.start_timestamp).split('.')[0]
    return cycles


def trigger_push_notification(push_subscription, title, body):
    try:
        response = webpush(
            subscription_info=json.loads(push_subscription.subscription_json),
            data=json.dumps({"title": title, "body": body}),
            vapid_private_key=current_app.config["PUSH_PRIVATE_KEY"],
            vapid_claims={"sub": "mailto:{}".format(current_app.config["PUSH_CLAIM_EMAIL"])}
        )
        return response.ok
    except WebPushException as ex:
        if ex.response and ex.response.json():
            extra = ex.response.json()
            print("Remote service replied with a {}:{}, {}", extra.code, extra.errno, extra.message)
        return False


def send_push_to_all(title, body):
    subscriptions = PushSubscription.query.all()
    return [trigger_push_notification(subscription, title, body) for subscription in subscriptions]


def send_push_to_user(user_id: int, title, body):
    subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    return [trigger_push_notification(subscription, title, body) for subscription in subscriptions]


def trigger_relay(mode: str):
    """Enable the relay on the Shelly device."""
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
    """ Queries Shelly Cloud API for energy consumption data in Watt-minute and return in kWatt-hour """
    consumption = requests.post(
        url="{}/device/status".format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
        params={
            'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
            'id': os.getenv('SHELLY_DEVICE_ID')
        }
    )

    if consumption.status_code != 200:
        raise Exception('Failed to get power consumption data from Shelly Cloud API')

    return consumption.json()['data']['device_status']['meters'][0]['total'] / 60000


def get_realtime_energy_consumption():
    """ Queries Shelly Cloud API for energy consumption data in Watt and return in kWatt """
    consumption = requests.post(
        url="{}/device/status".format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
        params={
            'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
            'id': os.getenv('SHELLY_DEVICE_ID')
        }
    )

    if consumption.status_code != 200:
        raise Exception('Failed to get power consumption data from Shelly Cloud API')

    return consumption.json()['data']['device_status']['meters'][0]['power']


def update_energy_consumption():
    """ Updates the energy consumption in the database """
    washing_machine = WashingMachine.query.first()
    washing_machine.currentkwh = get_energy_consumption()
    db.session.commit()
