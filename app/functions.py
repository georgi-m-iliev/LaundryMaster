import decimal, datetime

from flask import session

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
    """Calculate the charges for a user."""
    charges: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.user_id == user.id,
        WashingCycle.end_timestamp.is_not(None)
    ).all()

    result: decimal = 0
    for charge in charges:
        result += charge.cost

    return result


def calculate_usage(user: User) -> decimal:
    """Calculate the usage of electricity for a user."""
    usage: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.user_id == user.id,
        WashingCycle.end_timestamp.is_not(None)
    ).all()

    result: decimal = 0
    for use in usage:
        result += use.endkwh - use.startkwh

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
