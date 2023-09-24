import datetime

from flask import Blueprint, render_template, request, redirect, session
from flask_security import login_required, user_authenticated, current_user

from app.db import db
from app.models import User, WashingCycle
from app.functions import *

views = Blueprint('views', __name__)


@views.before_request
def handle_cycle_buttons():
    # if request is POST, then check if one of the buttons was pressed
    if request.method == 'POST':
        if request.form.get('start_cycle') is not None:
            start_cycle(current_user)
        if request.form.get('stop_cycle') is not None:
            stop_cycle(current_user)
        return redirect(request.path)

    # if request wasn't POST, then update the cycle information, to display proper buttons
    if current_user.is_authenticated:
        update_cycle(current_user)


@views.route('/', methods=['GET', 'POST'])
@views.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    return render_template(
        'index.html',
        is_dashboard=True,
        total_cost=calculate_charges(current_user),
        total_usage=calculate_usage(current_user),
        stopwatch=calculate_running_time(current_user)
    )


@views.route('/usage', methods=['GET', 'POST'])
@login_required
def usage_view():
    usages = WashingCycle.query.filter(
                WashingCycle.end_timestamp.is_not(None), WashingCycle.user_id == current_user.id
    ).order_by(WashingCycle.start_timestamp).limit(10).all()

    for usage in usages:
        usage.usedkwh = usage.endkwh - usage.startkwh
        usage.start_timestamp = usage.start_timestamp.strftime("%d/%m/%Y, %H:%M:%S")
        usage.end_timestamp = usage.end_timestamp.strftime("%d/%m/%Y, %H:%M:%S")
        end_parsed = datetime.datetime.strptime(usage.end_timestamp, "%d/%m/%Y, %H:%M:%S")
        start_parsed = datetime.datetime.strptime(usage.start_timestamp, "%d/%m/%Y, %H:%M:%S")
        usage.duration = end_parsed - start_parsed
    return render_template(
        'usage.html',
        is_usage=True,
        usages=usages
    )


@views.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    return render_template(
        'profile.html',
        is_profile=True
    )
