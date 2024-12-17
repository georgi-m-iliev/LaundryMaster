import decimal
import datetime

from sqlalchemy import or_, and_

from app.db import db
from app.models import User, roles_users
from app.models import WashingCycle, WashingCycleSplit, WashingMachine


def calculate_charges(user: User):
    """ Calculate the monthly charges for a user. """
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
        if split_users_count := len(charge.splits):
            charge.split_cost = round(charge.cost / (split_users_count + 1), 2)
            if charge.split_cost * (split_users_count + 1) < charge.cost:
                charge.split_cost = round(charge.split_cost + decimal.Decimal(0.01), 2)
            result += charge.split_cost
        else:
            result += charge.cost

    return result


def calculate_energy_usage(user: User = None):
    """ Calculate the monthly usage of electricity for a user. """
    if user is None:
        usage: list[WashingCycle] = WashingCycle.query.filter(
            WashingCycle.end_timestamp.is_not(None),
            db.func.extract('month', WashingCycle.end_timestamp) == datetime.datetime.now().month
        ).all()
    else:
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
        if split_user_count := len(use.splits):
            result += round((use.endkwh - use.startkwh) / (split_user_count + 1), 4)
        result += use.endkwh - use.startkwh

    return result


def calculate_unpaid_cycles_cost(user: User = None):
    """ Calculate the unpaid cycles for a user or at all. """
    if len(WashingCycle.query.all()) == 0:
        return 0
    if user is None:
        unpaid: list[WashingCycle] = WashingCycle.query.filter(
            WashingCycle.end_timestamp.is_not(None),
            WashingCycle.paid.is_(False),
            WashingCycle.user.has(active=True)
        )
        room_owner = db.session.query(roles_users).filter_by(role_id=3).first()
        if room_owner is not None:
            unpaid = unpaid.filter(WashingCycle.user_id != room_owner.user_id)
        unpaid = unpaid.all()
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

    result = 0
    for unpaid_cycle in unpaid:
        if split_users_count := len(unpaid_cycle.splits):
            unpaid_cycle.split_cost = round(unpaid_cycle.cost / (split_users_count + 1), 2)
            if unpaid_cycle.split_cost * (split_users_count + 1) < unpaid_cycle.cost:
                unpaid_cycle.split_cost = round(unpaid_cycle.split_cost + decimal.Decimal(0.01), 2)
            result += unpaid_cycle.split_cost
        else:
            result += unpaid_cycle.cost

    return result


def calculate_savings(user: User):
    """ Calculate the savings from having personal washing machine. """
    cycles: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_not(None),
        or_(
            WashingCycle.user_id == user.id,
            WashingCycle.splits.any(user_id=user.id)
        ),
        WashingCycle.cost > 0.30,  # minimum cost of washing and drying, so the calculation would be accurate
        db.func.extract('month', WashingCycle.end_timestamp) == datetime.datetime.now().month
    ).all()

    washing_machine = WashingMachine.query.first()
    if not washing_machine:
        return 0

    public_wash_cost = washing_machine.public_wash_cost

    result = 0
    for cycle in cycles:
        result += public_wash_cost - cycle.cost

    return result


def calculate_monthly_statistics(user: User, months: int = 6) -> dict:
    """ Calculate the monthly statistics for a user. """
    if months <= 0:
        return {"labels": [], "data": [0] * months}

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
            if split_users_count := len(cycle.splits):
                cycle.split_cost = round(cycle.cost / (split_users_count + 1), 2)
                if cycle.split_cost * (split_users_count + 1) < cycle.cost:
                    cycle.split_cost = round(cycle.split_cost + decimal.Decimal(0.01), 2)
                total_cost += cycle.split_cost
            else:
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
    users = User.query.filter_by(active=True).all()
    users_usage_stats = {'labels': [user.first_name for user in users], 'datasets': []}

    users_usage_stats['datasets'].append({
            'label': f'Cycles by user for the last {months} months',
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
            'label': f'Cycles by user for the last 30 days',
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


def users_unpaid_cycles_cost_statistics() -> dict:
    """ Calculates the unpaid cycles cost for each user. """

    def generate_color_by_user(user: User) -> str:
        """ Generates a random color for a user. """
        import hashlib
        hash_object = hashlib.md5(f"{user.id}{user.username}{user.email}".encode())
        hash_digest = hash_object.hexdigest()

        r = int(hash_digest[11:13], 16) % 128 + 127  # Red component
        g = int(hash_digest[2:4], 16) % 128 + 127  # Green component
        b = int(hash_digest[4:6], 16) % 128 + 127  # Blue component

        # Convert to hex format
        pastel_color = f"#{r:02x}{g:02x}{b:02x}"
        return pastel_color

    users = User.query.filter_by(active=True).all()
    users_unpaid_stats = {'labels': [user.first_name for user in users], 'datasets': []}

    users_unpaid_stats['datasets'].append({
        'label': 'Unpaid cycles cost by user',
        'fill': True,
        'data': [float(calculate_unpaid_cycles_cost(user)) for user in users],
        'backgroundColor': [generate_color_by_user(user) for user in users],
    })

    return users_unpaid_stats
