import datetime

from flask import Blueprint, render_template
from flask_security import login_required, user_authenticated, current_user

from app.db import db

from app.models import User, WashingCycle

views = Blueprint('views', __name__)


@views.route('/')
@views.route('/index')
@login_required
def index():
    print(current_user._get_current_object().username)
    return render_template('index.html', isDashboard=True)


@views.route('/usage')
@login_required
def usage():
    usages = WashingCycle.query.filter_by(user_id=current_user.id).limit(10).all()
    for usage in usages:
        usage.usedkwh = usage.endkwh - usage.startkwh
        usage.start_timestamp = usage.start_timestamp.strftime("%d/%m/%Y, %H:%M:%S")
        usage.end_timestamp = usage.end_timestamp.strftime("%d/%m/%Y, %H:%M:%S")
        usage.duration = datetime.datetime.strptime(usage.end_timestamp, "%d/%m/%Y, %H:%M:%S") - datetime.datetime.strptime(usage.start_timestamp, "%d/%m/%Y, %H:%M:%S")
        #TODO: actual calculation
        usage.cost = usage.usedkwh * 0.25
    return render_template('usage.html', isUsage=True, usages=usages)


@views.route('/profile')
@login_required
def profile():
    return render_template('profile.html', isProfile=True)
