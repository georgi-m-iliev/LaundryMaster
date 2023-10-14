import decimal, datetime, json, math
from flask import session, current_app
from pywebpush import webpush, WebPushException

from app.db import db
from app.models import User, WashingCycle, WashingMachine


def start_cycle(user: User):
    if WashingCycle.query.filter_by(endkwh=None, end_timestamp=None).all():
        # Cycle already running, display error
        pass
    else:
        # No cycle running, create new cycle
        new_cycle = WashingCycle(user_id=user.id, startkwh=WashingMachine.query.first().currentkwh)
        db.session.add(new_cycle)
        db.session.commit()
        session['cycle_id'] = new_cycle.id


def stop_cycle(user: User):
    if WashingCycle.query.filter_by(user_id=user.id, end_timestamp=None).all():
        # Cycle belonging to current user was found, stopping it
        cycle: WashingCycle = WashingCycle.query.filter_by(user_id=user.id, end_timestamp=None).first()
        cycle.endkwh = WashingMachine.query.first().currentkwh
        cycle.end_timestamp = db.func.current_timestamp()
        cycle.cost = (cycle.endkwh - cycle.startkwh) * WashingMachine.query.first().costperkwh
        db.session.commit()
        session.pop('cycle_id', None)
    else:
        # No cycle belonging to current user was found
        pass


def update_cycle(user: User):
    if WashingCycle.query.filter_by(user_id=user.id, end_timestamp=None).all():
        # Cycle belonging to current user was found, update view
        session['cycle_id'] = WashingCycle.query.filter_by(user_id=user.id, end_timestamp=None).first().id
    else:
        # No cycle belonging to current user was found, remove session variable
        session.pop('cycle_id', None)


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
    """Calculate the monthly unpaid cycles for a user."""
    unpaid: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.user_id == user.id,
        WashingCycle.end_timestamp.is_not(None),
        WashingCycle.paid.is_(False),
        db.func.extract('month', WashingCycle.end_timestamp) == datetime.datetime.now().month
    ).all()

    result: decimal = 0
    for unpaid_cycle in unpaid:
        result += unpaid_cycle.cost

    return result


def calculate_running_time(user: User) -> str:
    """Calculate the running time of the current cycle."""
    if 'cycle_id' in session:
        cycle: WashingCycle = WashingCycle.query.filter(
            WashingCycle.id == session['cycle_id'],
            WashingCycle.end_timestamp.is_(None)
        ).first()
        if cycle is not None:
            return str(datetime.datetime.now(datetime.timezone.utc) - cycle.start_timestamp).split('.')[0]
        else:
            return "None"
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
            vapid_claims={
                "sub": "mailto:{}".format(
                    current_app.config["PUSH_CLAIM_EMAIL"])
            }
        )
        return response.ok
    except WebPushException as ex:
        if ex.response and ex.response.json():
            extra = ex.response.json()
            print("Remote service replied with a {}:{}, {}",
                  extra.code,
                  extra.errno,
                  extra.message
                  )
        return False


def trigger_push_notifications_for_subscriptions(subscriptions, title, body):
    return [trigger_push_notification(subscription, title, body)
            for subscription in subscriptions]
