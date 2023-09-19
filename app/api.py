import os

from flask import Blueprint, request
from flask_security.utils import hash_password

from app.db import db
from app.auth import user_datastore

api = Blueprint('api', __name__)


@api.route('/')
def index():
    return '<h1>API</h1>'


@api.route('/adduser/>first_name>/<email>/<username>/<password>', methods=['POST'])
def update(email, username, password):
    if os.getenv('FLASK_API_SECRET_KEY') == request.headers.get('Authorization').split(' ')[1]:
        user_datastore.create_user(email=email, username=username, password=hash_password(password))
        db.session.commit()
        return {'status': 'success'}
    return {'status': 'invalid authenticator'}
