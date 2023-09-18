from flask import Blueprint

from app.db import db

from app.models import User

views = Blueprint('views', __name__)


@views.route('/')
def home():
    return '<h1>Home</h1>'
