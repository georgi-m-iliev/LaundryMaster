import os, json, time, datetime
from requests.exceptions import RequestException

from sqlalchemy.exc import OperationalError
from itsdangerous import URLSafeTimedSerializer

from flask import Blueprint, request, make_response, current_app, render_template, session, url_for
from flask_security import login_required, roles_required, current_user
from flask_security.utils import hash_password
from flask_sock import Sock

from app.db import db
from app.auth import user_datastore

from app.models import User, WashingMachine, PushSubscription, WashingCycle, NotificationURL, ScheduleEvent, CeleryTask
from app.functions import send_push_to_all, send_push_to_user, get_realtime_current_usage, get_running_time
from app.functions import get_washer_info, get_relay_temperature, get_relay_wifi_rssi
from app.candy import CandyWashingMachine

api = Blueprint('api', __name__)
sock = Sock()


@api.errorhandler(OperationalError)
def handle_db_error(error):
    return {'status': 'database error', 'error': str(error)}, 503


@api.route('/')
def index():
    return '<h1>API</h1>'


@api.route('/db_alive')
def db_alive():
    # Exception would be raised if the database is not available, no need to query any data
    return {'status': 'success'}


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
        user=User.query.filter_by(id=user_id).first(),
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
def ws_washing_machine_info(ws):
    if request.args.get('shelly') == 'false':
        shelly = False
    else:
        shelly = True

    while True:
        try:
            ws.send(json.dumps(get_washer_info(shelly)))
            time.sleep(1)
        except RequestException as ex:
            current_app.logger.error(f'Error fetching washing machine info. Error: {ex}')
            return


@api.route('/export_washing_cycles.csv', methods=['GET'])
@login_required
@roles_required('admin')
def export_washing_cycles():
    query = WashingCycle.query.filter(WashingCycle.end_timestamp.is_not(None))
    if request.args.get('count'):
        query.limit(request.args.get('count'))

    cycles: list[WashingCycle] = query.order_by(WashingCycle.start_timestamp.desc()).all()

    csv = 'id,user,date,used_kwh,cost\n'
    for cycle in cycles:
        csv += f'{cycle.id},{cycle.user_id},{cycle.start_timestamp.strftime("%Y-%m-%d")},{cycle.endkwh - cycle.startkwh},{cycle.cost}\n'
    if request.args.get('excel'):
        csv = csv.replace(',', ';').replace('.', ',')
    output = make_response(csv)
    output.headers["Content-Disposition"] = "attachment"
    output.headers["Content-type"] = "text/csv"
    return output


@api.route('/get_candy_data', methods=['GET'])
@login_required
@roles_required('admin')
def get_candy_data():
    machine = CandyWashingMachine()
    return {'result': machine.json()}


@sock.route('/api/candy_data')
@login_required
def ws_candy_data(ws):
    interval = 60
    if request.args.get('interval'):
        interval = int(request.args.get('interval'))

    machine = CandyWashingMachine()
    while True:
        ws.send(machine.json())
        time.sleep(interval)
        machine.update()


@api.route('/schedule_events', methods=['POST'])
@login_required
def schedule_events_post():
    event = ScheduleEvent(
        user_id=current_user.id,
        start_timestamp=datetime.datetime.strptime(request.form['start_date'], '%Y-%m-%d %H:%M'),
        end_timestamp=datetime.datetime.strptime(request.form['end_date'], '%Y-%m-%d %H:%M'),
    )
    db.session.add(event)
    db.session.commit()
    CeleryTask.start_schedule_notification_task(current_user.id, event.id, event.start_timestamp, session['timezone'])
    return {'action': 'post'}


@api.route('/schedule_events/<event_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def schedule_events(event_id: int):
    event = ScheduleEvent.query.filter_by(id=event_id).first()
    if not event:
        return {'action': 'error', 'tid': {'message': 'Event not found!'}}, 404
    if not current_user.has_role('admin') and current_user != event.user:
        return {'action': 'error', 'tid': {'message': 'Action unauthorized!'}}, 403

    if request.method == 'GET':
        return {'action': 'get', 'tid': {
            'id': event.id,
            'start_date': event.start_timestamp.strftime('%Y-%m-%d %H:%M'),
            'end_date': event.end_timestamp.strftime('%Y-%m-%d %H:%M'),
            'text': event.text,
            'color': '7fc2d1'
        }}
    elif request.method == 'PUT':
        event.start_timestamp = datetime.datetime.strptime(request.form['start_date'], '%Y-%m-%d %H:%M')
        event.end_timestamp = datetime.datetime.strptime(request.form['end_date'], '%Y-%m-%d %H:%M')
        if event.notification_task:
            event.notification_task.terminate()
            CeleryTask.start_schedule_notification_task(event.user_id, event.id, event.start_timestamp, session['timezone'])
        db.session.commit()
        return {'action': 'put'}
    elif request.method == 'DELETE':
        if event.notification_task:
            event.notification_task.terminate()
        db.session.delete(event)
        db.session.commit()
        return {'action': 'delete'}


@api.route('/get_guest_totp_url', methods=['GET'])
@login_required
@roles_required('admin')
def get_guest_totp_url():
    if not request.args.get('user_id'):
        return {'error': 'invalid args'}

    user = User.query.filter_by(id=request.args.get('user_id')).first()
    if not user:
        return {'error': 'user not found'}

    user.active = True
    db.session.commit()

    serializer = URLSafeTimedSerializer(os.getenv('FLASK_SECRET_KEY'))
    token = serializer.dumps(user.id, salt='login-request')

    login_url = url_for('auth.token_login', token=token, _external=True)

    return {'url': login_url}
