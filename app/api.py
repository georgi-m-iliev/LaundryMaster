import os, json

from flask import Blueprint, request
from flask_security.utils import hash_password

from app.db import db
from app.auth import user_datastore

from app.models import User

api = Blueprint('api', __name__)


@api.route('/')
def index():
    return '<h1>API</h1>'


@api.route('/adduser', methods=['POST'])
def update():
    if os.getenv('FLASK_API_SECRET_KEY') == request.headers.get('Authorization').split(' ')[1]:
        user_datastore.create_user(
            first_name=request.form['first_name'],
            email=request.form['email'],
            username=request.form['username'],
            password=hash_password(request.form['password'])
        )
        db.session.commit()
        return {'status': 'success'}
    return {'status': 'invalid authenticator'}


@api.route('/resetpass', methods=['POST'])
def reset_password():
    if os.getenv('FLASK_API_SECRET_KEY') == request.headers.get('Authorization').split(' ')[1]:
        user = User.query.filter_by(username=request.form['username']).first()
        user.password = hash_password(request.form['password'])
        db.session.commit()
        return {'status': 'success'}
    return {'status': 'invalid authenticator'}
