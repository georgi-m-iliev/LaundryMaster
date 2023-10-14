import os, json

from flask import Blueprint, request
from flask_security.utils import hash_password

from app.db import db
from app.auth import user_datastore

from app.models import User, WashingMachine, PushSubscription
from app.functions import trigger_push_notifications_for_subscriptions

api = Blueprint('api', __name__)


@api.route('/')
def index():
    return '<h1>API</h1>'


@api.route('/add_user', methods=['POST'])
def adduser():
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


@api.route('/reset_password', methods=['POST'])
def reset_password():
    if os.getenv('FLASK_API_SECRET_KEY') == request.headers.get('Authorization').split(' ')[1]:
        user = User.query.filter_by(username=request.form['username']).first()
        user.password = hash_password(request.form['password'])
        db.session.commit()
        return {'status': 'success'}
    return {'status': 'invalid authenticator'}


@api.route('/update_usage', methods=['PATCH'])
def update_usage():
    if os.getenv('FLASK_API_SECRET_KEY') == request.headers.get('Authorization').split(' ')[1]:
        washing_machine = WashingMachine.query.first()
        washing_machine.currentkwh = request.args.get('currentkwh')
        db.session.commit()
        return {'status': 'success'}
    return {'status': 'invalid authenticator'}


@api.route('/get_usage', methods=['GET'])
def get_usage():
    return {'currentkwh': WashingMachine.query.first().currentkwh}


@api.route('/push_subscriptions', methods=['POST'])
def push_subscriptions():
    json_data = request.get_json()
    subscription = PushSubscription.query.filter_by(subscription_json=json_data['subscription_json']).first()
    if subscription is None:
        subscription = PushSubscription(subscription_json=json_data['subscription_json'])
        db.session.add(subscription)
        db.session.commit()
    return {"status": "success"}


@api.route('/trigger_push', methods=['POST'])
def trigger_push():
    json_data = request.get_json()
    subscriptions = PushSubscription.query.all()
    results = trigger_push_notifications_for_subscriptions(
        subscriptions,
        json_data.get('title'),
        json_data.get('body')
    )
    return {"status": "success"}
