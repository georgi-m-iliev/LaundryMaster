import os, json, time

from flask import Blueprint, request, make_response
from flask_security import login_required, roles_required, current_user
from flask_security.utils import hash_password
from flask_sock import Sock

from app.db import db
from app.auth import user_datastore

from app.models import User, WashingMachine, PushSubscription, UserSettings, WashingCycle, NotificationURL
from app.functions import send_push_to_all, send_push_to_user, get_realtime_current_usage, get_running_time
from app.functions import get_washer_info, get_relay_temperature, get_relay_wifi_rssi

api = Blueprint('api', __name__)
sock = Sock()


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
        settings = UserSettings(user_id=User.query.filter_by(username=request.form['username']).first().id)
        db.session.add(settings)
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
@login_required
def get_usage():
    return {'currentkwh': WashingMachine.query.first().currentkwh}


@api.route('/push_subscriptions', methods=['POST'])
@login_required
def push_subscriptions():
    json_data = request.get_json()
    subscription = PushSubscription.query.filter_by(subscription_json=json_data['subscription_json']).first()
    if subscription is None:
        subscription = PushSubscription(
            subscription_json=json_data['subscription_json'],
            user_id=json_data['user_id']
        )
        db.session.add(subscription)
        db.session.commit()
    return {"status": "success"}


@api.route('/trigger_push', methods=['POST'])
@login_required
@roles_required('admin')
def trigger_push():
    json_data = request.get_json()
    send_push_to_all(
        notification=NotificationURL(
            title=json_data.get('title'),
            body=json_data.get('body'),
            icon=json_data.get('icon', None),
            url=json_data.get('url', '/')
        )
    )
    return {"status": "success"}


@api.route('/trigger_push/<user_id>', methods=['POST'])
@login_required
@roles_required('admin')
def trigger_push_by_id(user_id: int):
    json_data = request.get_json()
    send_push_to_user(
        user=User.query.get(user_id),
        notification=NotificationURL(
            title=json_data.get('title'),
            body=json_data.get('body'),
            icon=json_data.get('icon', None),
            url=json_data.get('url', '/')
        )
    )
    return {"status": "success"}


@api.route('/washing_machine/running_time', methods=['GET'])
@login_required
def running_time():
    return {'value': get_running_time()}


@api.route('/washing_machine/current_energy_consumption', methods=['GET'])
@login_required
def current_energy_consumption():
    return {'value': get_realtime_current_usage()}


@api.route('/washing_machine/relay_temperature', methods=['GET'])
@login_required
def relay_temperature():
    return {'value': get_relay_temperature()}


@api.route('/washing_machine/relay_wifi_rssi', methods=['GET'])
@login_required
def relay_wifi_rssi():
    return {'value': get_relay_wifi_rssi()}


@sock.route('/api/washing_machine_infos')
@login_required
def websocket(ws):
    if request.args.get('shelly') == 'false':
        shelly = False
    else:
        shelly = True

    while True:
        ws.send(json.dumps(get_washer_info(shelly)))
        time.sleep(1)


@api.route('/export_washing_cycles.csv', methods=['GET'])
@login_required
@roles_required('admin')
def export_washing_cycles():
    cycles: list[WashingCycle] = WashingCycle.query.all()
    csv = 'id,user,date,used_kwh,cost\n'
    for cycle in cycles:
        csv += f'{cycle.id},{cycle.user_id},{cycle.start_timestamp.strftime("%Y-%m-%d")},{cycle.endkwh - cycle.startkwh},{cycle.cost}\n'
    if request.args.get('excel'):
        csv = csv.replace(',', ';').replace('.', ',')
    output = make_response(csv)
    output.headers["Content-Disposition"] = "attachment"
    output.headers["Content-type"] = "text/csv"
    return output
