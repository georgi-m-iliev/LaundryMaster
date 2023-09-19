from flask import Blueprint, render_template
from flask_security import login_required, user_authenticated

from app.db import db

from app.models import User

views = Blueprint('views', __name__)


@views.route('/')
@views.route('/index')
@login_required
def index():
    return render_template('index.html', isDashboard=True)


@views.route('/usage')
@login_required
def usage():
    return render_template('usage.html', isUsage=True)


@views.route('/profile')
@login_required
def profile():
    return render_template('profile.html', isProfile=True)
