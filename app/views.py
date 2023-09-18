from flask import Blueprint, render_template

from app.db import db

from app.models import User

views = Blueprint('views', __name__)


@views.route('/')
@views.route('/index')
def index():
    return render_template('index.html', isDashboard=True)


@views.route('/usage')
def usage():
    return render_template('usage.html', isUsage=True)


@views.route('/profile')
def profile():
    return render_template('profile.html', isProfile=True)
