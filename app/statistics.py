import datetime

from sqlalchemy import or_, and_

from app import User, db
from app.models import WashingCycle, WashingCycleSplit, WashingMachine


def calculate_charges(user: User):
    """Calculate the monthly charges for a user."""
    charges: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_not(None),
        or_(
            WashingCycle.user_id == user.id,
            WashingCycle.splits.any(user_id=user.id)
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
            WashingCycle.splits.any(user_id=user.id)
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
                WashingCycle.splits.any(user_id=user.id, paid=False)
            )
        ).all()

        # paid_split_cycles_ids = [cycle.cycle_id for cycle in db.session.query(split_cycles).filter_by(
        #     user_id=user.id, paid=True
        # ).all()]
        # unpaid = [cycle for cycle in unpaid if cycle.id not in paid_split_cycles_ids]

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
            WashingCycle.splits.any(user_id=user.id)
        ),
        WashingCycle.cost > 0.30,  # minimum cost of washing and drying, so the calculation would be accurate
        db.func.extract('month', WashingCycle.end_timestamp) == datetime.datetime.now().month
    ).all()

    public_wash_cost = WashingMachine.query.first().public_wash_cost

    result = 0
    for cycle in cycles:
        result += public_wash_cost - cycle.cost

    return result


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
                WashingCycle.splits.any(user_id=user.id)
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


def admin_users_usage_statistics(months: int = 12) -> dict:
    """ Calculates the times each user has used the washing machine. """
    users = User.query.all()
    users_usage_stats = {'labels': [user.first_name for user in users], 'datasets': []}

    users_usage_stats['datasets'].append({
            'label': f'Cycles per user for the last {months} months',
            'fill': True,
            'data': [],
            'backgroundColor': '#5f74d7',
    })
    for user in users:
        cycles = WashingCycle.query.filter(
            WashingCycle.user_id == user.id,
            WashingCycle.start_timestamp >= datetime.datetime.now() - datetime.timedelta(days=months * 30)
        ).all()
        users_usage_stats['datasets'][0]['data'].append(len(cycles))

    users_usage_stats['datasets'].append({
            'label': f'Cycles per user for the last 30 days',
            'fill': True,
            'data': [],
            'backgroundColor': '#7fc2d1',
    })
    for user in users:
        cycles = WashingCycle.query.filter(
            WashingCycle.user_id == user.id,
            WashingCycle.start_timestamp >= datetime.datetime.now() - datetime.timedelta(days=30)
        ).all()
        users_usage_stats['datasets'][1]['data'].append(len(cycles))

    return users_usage_stats
