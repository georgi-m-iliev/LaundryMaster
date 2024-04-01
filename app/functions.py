import os, decimal, datetime, json, requests, time, pytz
from requests.exceptions import RequestException

from flask import current_app, flash, request, redirect, session
from flask_security import roles_required
from pywebpush import webpush, WebPushException
from sqlalchemy import or_, and_
from requests_cache import CachedSession, RedisCache

from app.db import db
from app.auth import user_datastore
from app.models import User, WashingCycle, WashingCycleSplit, WashingMachine, PushSubscription, CeleryTask, WashingCyclePayment
from app.models import Notification, SplitRequestNotification, unpaid_cycles_reminder_notification, ScheduleEvent, NotificationURL
from app.forms import SplitCycleForm
from app.statistics import calculate_unpaid_cycles_cost


def start_cycle(user: User):
    """ Initiates a new cycle for a user. """
    if WashingCycle.query.filter_by(endkwh=None, end_timestamp=None).all():
        # User has an already running cycle
        current_app.logger.error(f"User {user.username} tried to start a cycle, but one was already active.")
        flash('You already have a cycle running!', category='toast-warning')
        raise ChildProcessError('User already has a cycle running!')

    washing_machine = WashingMachine.query.first()

    if washing_machine.require_scheduling:
        now = datetime.datetime.now(pytz.timezone(session['timezone']))
        event = ScheduleEvent.query.filter(
            ScheduleEvent.start_timestamp <= now,
            ScheduleEvent.end_timestamp >= now,
            ScheduleEvent.user_id == user.id
        ).first()

        if not event and not (user.has_role('room_owner') or user.has_role('admin')):
            current_app.logger.error(f"User {user.username} tried to start a cycle, but there is no scheduled event.")
            flash('You did not schedule your washing! Cannot proceed.', category='toast-warning')
            raise ChildProcessError('User does not have a scheduled event!')

    # No cycle running, create new cycle
    current_app.logger.info(f'User {user.username} is starting a new cycle.')

    try:
        if trigger_relay('on') != 200:
            current_app.logger.error("Request to turn on the relay through Shelly Cloud API FAILED!")
            flash('Request to turn on the relay failed!\nPlease try again!', category='toast-error')
            raise ChildProcessError('Request to turn on the relay failed!')
    except requests.exceptions.ConnectionError:
        current_app.logger.error("Shelly Cloud API request failed! API is probably down...")
        flash('Request to turn off the relay failed!\nPlease try again!', category='toast-error')
        raise ChildProcessError('Request to turn off the relay failed!')

    try:
        new_cycle = WashingCycle(user_id=user.id, startkwh=get_energy_consumption())
        db.session.add(new_cycle)
        db.session.commit()
        current_app.logger.info(f'User {user.username} successfully started a new cycle.')
        flash('Cycle successfully started!', category='toast-success')
        db.session.refresh(new_cycle)

        CeleryTask.start_cycle_end_notification_task(user.id, new_cycle.id)

    except RequestException:
        current_app.logger.error(f'Error with initialising a cycle for user {user.username}.')
        flash('Unexpected error occurred!\nPlease try again!', category='toast-error')
        db.session.rollback()
        raise ChildProcessError('Error with initialising a cycle for user {user.username}.')


def stop_cycle(user: User):
    """ Terminates the running cycle for a user. """
    cycle: WashingCycle = WashingCycle.query.filter_by(user_id=user.id, end_timestamp=None).first()
    if cycle:
        # Cycle belonging to current user was found, stopping it
        current_app.logger.info(f'User {user.username} is stopping their cycle.')

        try:
            if trigger_relay('off') != 200:
                current_app.logger.error("Request to turn off the relay through Shelly Cloud API FAILED!")
                flash('Request to turn off the relay failed!\nPlease try again!', category='toast-error')
                raise ChildProcessError('Request to turn off the relay failed!')
        except requests.exceptions.ConnectionError:
            current_app.logger.error("Shelly Cloud API request failed! API is probably down...")
            flash('Request to turn off the relay failed!\nPlease try again!', category='toast-error')
            raise ChildProcessError('Request to turn off the relay failed!')

        try:
            update_energy_consumption()
            cycle.endkwh = WashingMachine.query.first().currentkwh
            cycle.end_timestamp = db.func.current_timestamp()
            cycle.cost = (cycle.endkwh - cycle.startkwh) * WashingMachine.query.first().costperkwh

            try:
                if cycle.notification_task:
                    current_app.logger.info('Stopping cycle end notification task...')
                    cycle.notification_task.terminate()
            except Exception as e:
                current_app.logger.error(f'Error with stopping cycle end notification task... {e}')

            if cycle.cost == 0:
                db.session.delete(cycle)

            db.session.commit()
            current_app.logger.info(f'User {user.username} successfully stopped their cycle.')
            flash('Cycle successfully terminated!', category='toast-success')
        except RequestException:
            current_app.logger.error(
                f'Error with terminating a cycle for user {user.username} due to failure of energy consumption update.')
            flash('Unexpected error occurred!\nPlease try again!', category='toast-error')
            raise ChildProcessError('Error with updating energy consumption!')
        except Exception as e:
            current_app.logger.error(f'Error with terminating a cycle for user {user.username}. {e.__str__()}')
            flash('Unexpected error occurred!\nPlease try again!', category='toast-error')
            raise ChildProcessError('Error with terminating a cycle.')
    else:
        current_app.logger.error(f"User {user.username} tried to stop a cycle, but they didn't start one.")
        flash('You do not have a running cycle!', category='toast-warning')
        raise ChildProcessError('User does not have a running cycle!')


def update_cycle(user: User):
    """ Updates the running cycle for a user. Should be executed on every request. """
    cycle = WashingCycle.query.filter_by(end_timestamp=None).first()
    if cycle:
        if cycle.user_id == user.id:
            return {'state': 'running', 'id': cycle.id}
        else:
            return {'state': 'unavailable', 'id': None, 'user': cycle.user.first_name}
    else:
        return {'state': 'available', 'id': None}


def get_running_time() -> str:
    """ Calculate the running time of the current cycle. """
    cycle: WashingCycle = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_(None)
    ).first()
    if cycle is not None:
        return str(datetime.datetime.now(datetime.timezone.utc) - cycle.start_timestamp).split('.')[0].zfill(8)
    else:
        return '00:00:00'


def get_remaining_minutes() -> int:
    """ Fetch the remaining minutes of the current cycle. """
    washing_machine: WashingMachine = WashingMachine.query.first()
    if washing_machine.candy_appliance_data is None:
        return 0
    elif 'remaining_minutes' not in washing_machine.candy_appliance_data:
        return 0

    return washing_machine.candy_appliance_data['remaining_minutes']


def get_unpaid_list(user: User):
    """ Get the unpaid cycles for a user. """
    cycles: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_not(None),
        or_(
            and_(
                WashingCycle.user_id == user.id,
                WashingCycle.paid.is_(False),
            ),
            WashingCycle.splits.any(user_id=user.id, paid=False)
        )
    ).order_by(WashingCycle.start_timestamp.desc(), WashingCycle.end_timestamp.desc()).all()

    for cycle in cycles:
        if split_users_count := len(cycle.splits):
            cycle.split_cost = round(cycle.cost / (split_users_count + 1), 2)
            if cycle.split_cost * (split_users_count + 1) < cycle.cost:
                cycle.split_cost = round(cycle.split_cost + decimal.Decimal(0.01), 2)
            cycle.split_paid = False
        cycle.start_timestamp_formatted = cycle.start_timestamp.strftime("%d-%m-%Y %H:%M:%S")
        cycle.end_timestamp_formatted = cycle.end_timestamp.strftime("%d-%m-%Y %H:%M:%S")
    return cycles


def get_usage_list(user: User, limit: int = 10):
    """ Get the usage list for a user. """
    cycles: list[WashingCycle] = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_not(None),
        or_(
            WashingCycle.user_id == user.id,
            WashingCycle.splits.any(user_id=user.id)
        )
    ).order_by(WashingCycle.start_timestamp.desc(), WashingCycle.end_timestamp.desc()).limit(limit).all()

    for cycle in cycles:
        cycle.usedkwh = round(cycle.endkwh - cycle.startkwh, 2)
        if split_users_count := len(cycle.splits):
            # print(cycle.splits)
            cycle.split_cost = round(cycle.cost / (split_users_count + 1), 2)
            if cycle.split_cost * (split_users_count + 1) < cycle.cost:
                cycle.split_cost = round(cycle.split_cost + decimal.Decimal(0.01), 2)
            if cycle.user_id != user.id:
                cycle.split_paid = WashingCycleSplit.query.filter_by(cycle_id=cycle.id, user_id=user.id).first().paid
        cycle.start_timestamp_formatted = cycle.start_timestamp.strftime("%d-%m-%Y %H:%M:%S")
        cycle.end_timestamp_formatted = cycle.end_timestamp.strftime("%d-%m-%Y %H:%M:%S")
        cycle.duration = str(cycle.end_timestamp - cycle.start_timestamp).split('.')[0]
    return cycles


def trigger_push_notification(push_subscription, notification: Notification):
    """ Sends a push notification through a push subscription. """
    try:
        response = webpush(
            subscription_info=json.loads(push_subscription.subscription_json),
            data=json.dumps(notification.__dict__()),
            vapid_private_key=current_app.config["PUSH_PRIVATE_KEY"],
            vapid_claims={"sub": "mailto:{}".format(current_app.config["PUSH_CLAIM_EMAIL"])}
        )
        return response.ok
    except WebPushException as ex:
        current_app.logger.error(f'Error trying to send notification.')
        if ex.response and ex.response.json():
            extra = ex.response.json()
            current_app.logger.error("Remote service replied with a {}:{}, {}", extra.code, extra.errno, extra.message)
        return False


def send_push_to_all(notification: Notification):
    """ Sends push to all users through all push subscriptions. """
    current_app.logger.info('Sending push notification to all users.')
    subscriptions = PushSubscription.query.all()
    return [trigger_push_notification(subscription, notification) for subscription in subscriptions]


def send_push_to_user(user: User, notification: Notification):
    """ Sends push to a user through all push subscriptions associated with them. """
    current_app.logger.info(f'Sending push notification to {user.username}.')
    subscriptions = PushSubscription.query.filter_by(user_id=user.id).all()
    return [trigger_push_notification(subscription, notification) for subscription in subscriptions]


def trigger_relay(mode: str):
    """ Changes the relay state of a Shelly device. """
    current_app.logger.info(f'Triggering relay through Shelly API to be {mode}.')
    response = requests.post(
        url='{}/device/relay/control'.format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
        data={
            'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
            'id': os.getenv('SHELLY_DEVICE_ID'),
            'channel': '0',
            'turn': 'on' if mode == 'on' else 'off'
        })
    return response.status_code


def get_energy_consumption():
    """ Queries Shelly Cloud API for energy consumption data in Watt-minute and returns in kWatt-hour. """
    data = requests.get(
        url="{}/device/status".format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
        params={
            'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
            'id': os.getenv('SHELLY_DEVICE_ID')
        }
    )

    if data.status_code != 200:
        current_app.logger.error('Failed to get power consumption data from Shelly Cloud API')
        raise RequestException('Failed to get power consumption data from Shelly Cloud API')

    return data.json()['data']['device_status']['meters'][0]['total'] / 60000


def get_realtime_current_usage():
    """ Queries Shelly Cloud API for current usage data in Watt. """
    data = requests.get(
        url="{}/device/status".format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
        params={
            'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
            'id': os.getenv('SHELLY_DEVICE_ID')
        }
    )

    if data.status_code != 200:
        current_app.logger.error('Failed to get current usage data from Shelly Cloud API')
        raise RequestException('Failed to get current usage data from Shelly Cloud API')

    return data.json()['data']['device_status']['meters'][0]['power']


def update_energy_consumption():
    """ Updates the energy consumption in the database """
    washing_machine = WashingMachine.query.first()
    washing_machine.currentkwh = get_energy_consumption()
    db.session.commit()


def get_relay_temperature():
    """ Queries Shelly Cloud API for relay temperature in Celsius. """
    data = requests.get(
        url="{}/device/status".format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
        params={
            'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
            'id': os.getenv('SHELLY_DEVICE_ID')
        }
    )

    if data.status_code != 200:
        raise RequestException('Failed to get data from Shelly Cloud API')

    return data.json()['data']['device_status']['temperature']


def get_relays_state():
    """ Queries Shelly Cloud API for relay state. """
    data = requests.get(
        url="{}/device/status".format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
        params={
            'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
            'id': os.getenv('SHELLY_DEVICE_ID')
        }
    )

    if data.status_code != 200:
        raise RequestException('Failed to get data from Shelly Cloud API')

    return data.json()['data']['device_status']['relays'][0]['ison']


def get_relay_wifi_rssi():
    """ Queries Shelly Cloud API for relay Wi-Fi RSSI. """
    data = requests.get(
        url="{}/device/status".format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
        params={
            'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
            'id': os.getenv('SHELLY_DEVICE_ID')
        }
    )

    if data.status_code != 200:
        raise RequestException('Failed to get data from Shelly Cloud API')

    return data.json()['data']['device_status']['wifi_sta']['rssi']


def get_washer_info(shelly=True):
    """ Returns a dict with washing machine information """
    if shelly:
        cache_session = CachedSession(
            backend=RedisCache() if not current_app.debug else 'sqlite',
            cache_name='shelly_cache',
            expire_after=1 if current_app.debug else 30
        )
        shelly_request = cache_session.get(
            url="{}/device/status".format(os.getenv('SHELLY_CLOUD_ENDPOINT')),
            params={
                'auth_key': os.getenv('SHELLY_CLOUD_AUTH_KEY'),
                'id': os.getenv('SHELLY_DEVICE_ID')
            }
        )

        if shelly_request.status_code != 200:
            current_app.logger.error('Failed to get current usage data from Shelly Cloud API')
            raise RequestException('Failed to get current usage data from Shelly Cloud API')

        shelly_data = shelly_request.json()

        return {
            "running_time": get_running_time(),
            "remaining_minutes": get_remaining_minutes(),
            "current_usage": shelly_data['data']['device_status']['meters'][0]['power'],
            "relay_ison": shelly_data['data']['device_status']['relays'][0]['ison'],
            "relay_temperature": shelly_data['data']['device_status']['temperature'],
            "relay_wifi_rssi": shelly_data['data']['device_status']['wifi_sta']['rssi']
        }

    return {"running_time": get_running_time()}


def delete_user(user: User):
    """ Deletes a user and all associated data excl. washing cycles. """
    from app.models import User, UserSettings, PushSubscription, ScheduleEvent, WashingCycle, WashingCycleSplit, \
        roles_users
    UserSettings.query.filter_by(user_id=user.id).delete()
    PushSubscription.query.filter_by(user_id=user.id).delete()
    ScheduleEvent.query.filter_by(user_id=user.id).delete()
    cycles = WashingCycle.query.filter_by(user_id=user.id).all()
    WashingCycleSplit.query.filter_by(user_id=user.id, paid=False).delete()

    for cycle in cycles:
        cycle.user_id = None

    roles_users.delete().where(roles_users.c.user_id == user.id)
    user_datastore.delete_user(user)

    db.session.commit()


def split_cycle(user: User, split_cycle_form: SplitCycleForm):
    """ Splits a cycle between users based on passed SplitCycleForm. """
    cycle: WashingCycle = WashingCycle.query.filter_by(id=split_cycle_form.cycle_id.data).first()
    if cycle.user_id != user.id:
        flash('You can only split your own cycles', category='toast-error')
    elif cycle.paid:
        flash('You cannot split paid cycles', category='toast-error')
    else:
        if cycle.splits:
            # if there are paid splits, then we cannot proceed
            paid_splits = [split for split in cycle.splits if split.paid]
            if len(paid_splits) > 0:
                flash('You cannot split cycles that have paid splits', category='toast-error')
                return redirect(request.path)

        users_already_split = [split.user_id for split in cycle.splits]
        for split_participant_user_id in split_cycle_form.other_users.data:
            if split_participant_user_id in users_already_split:
                # user is already in split, so we skip them
                continue
            split_participant = User.query.filter_by(id=split_participant_user_id).first()
            cycle.splits.append(WashingCycleSplit(cycle_id=cycle.id, user_id=split_participant_user_id))
            send_push_to_user(split_participant, SplitRequestNotification(user, cycle))
        db.session.commit()
        flash('Cycle split successfully, users need to confirm to complete!', category='toast-success')


def mark_cycle_paid(user: User, cycle_id: int, mass_marking: bool = False):
    """ Marks a cycle as paid. """
    cycle = WashingCycle.query.filter_by(id=cycle_id).first()
    if cycle is None:
        flash(f'Cycle #{cycle_id} not found', category='toast-error')
    elif [split.accepted for split in cycle.splits].count(False):
        flash(f'Cycle #{cycle_id} couldn\'t be marked as paid!'
              'You can mark the cycle as paid only after all users have accepted the split', category='toast-warning')
    elif cycle.user_id != user.id:
        split = WashingCycleSplit.query.filter_by(
            cycle_id=cycle_id,
            user_id=user.id
        ).first()
        if split:
            if split.accepted:
                split.paid = True
                db.session.commit()
                if not mass_marking:
                    flash(f'Cycle #{cycle_id} marked as paid', category='toast-success')
                return True
            else:
                flash(f'Cycle #{cycle_id} couldn\'t be marked as paid!'
                      'You can only mark accepted cycles as paid', category='toast-error')
        else:
            flash(f'Cycle #{cycle_id} couldn\'t be marked as paid!'
                  'You can only mark your own cycles as paid', category='toast-error')
    elif cycle.paid:
        flash(f'Cycle #{cycle_id} already marked as paid', category='toast-error')
    else:
        cycle.paid = True
        db.session.commit()
        if not mass_marking:
            flash(f'Cycle #{cycle_id} marked as paid', category='toast-success')
        return True

    return False


def notify_debtors():
    """ Sends push notifications to all users owing money. """
    if calculate_unpaid_cycles_cost() < os.getenv('DEBTS_THRESHOLD', 5):
        current_app.logger.info('Debts are below the threshold, no notifications sent.')
        return
    room_owner = User.query.filter(User.roles.any(name='room_owner')).first()
    debtors = {cycle.user for cycle in WashingCycle.query.filter_by(paid=False).all()} - {room_owner}
    for debtor in debtors:
        send_push_to_user(user=debtor, notification=unpaid_cycles_reminder_notification)


def recalculate_cycles_cost():
    """ Recalculates the cost of all unpaid cycles based on new price per kWh. """
    if current_app.debug:
        current_app.logger.warning('We are debugging, no changes applied to the database.')
        return

    # Grace period to terminate the task if it's a mistake
    time.sleep(10 * 60)

    recalc_cycles = WashingCycle.query.filter(
        WashingCycle.end_timestamp.is_not(None),
        WashingCycle.paid.is_(False)
    ).all()

    for cycle in recalc_cycles:
        cycle.cost = (cycle.endkwh - cycle.startkwh) * WashingMachine.query.first().costperkwh

    db.session.commit()


def schedule_check_for_overlapping(start_timestamp: datetime.datetime, end_timestamp: datetime.datetime, event_id):
    """ Checks if there are any existing events in the schedule for the interval. """
    overlapping_events = ScheduleEvent.query.filter(
        ScheduleEvent.id != event_id,
        or_(and_(start_timestamp >= ScheduleEvent.start_timestamp,
                 start_timestamp <= ScheduleEvent.end_timestamp),
            and_(end_timestamp >= ScheduleEvent.start_timestamp,
                 end_timestamp <= ScheduleEvent.end_timestamp)
            )
    ).all()

    return len(overlapping_events) > 0


def schedule_create_new_event(start_timestamp: datetime.datetime, end_timestamp: datetime.datetime, user: User):
    """ Creates a new event in the schedule. """
    # get number of events for the user for the current week
    user_events = ScheduleEvent.query.filter(
        ScheduleEvent.user_id == user.id,
        ScheduleEvent.timestamp >= datetime.datetime.now() - datetime.timedelta(hours=4)
    ).all()

    if len(user_events) >= 3:
        raise PermissionError('Too many requests in a short timespan.')

    event = ScheduleEvent(
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
        user_id=user.id
    )
    db.session.add(event)
    db.session.commit()

    CeleryTask.start_schedule_notification_task(user.id, event.id, start_timestamp, session['timezone'])

    interested_users = User.query.filter(User.roles.any(name='room_owner')).all()
    for interested_user in interested_users:
        send_push_to_user(interested_user, NotificationURL(
            title=f'{user.first_name} scheduled washing on {start_timestamp.strftime("%d-%m at %H:%M")}.',
            body='Go check the schedule for more details.',
            icon='cycle-reminder-icon.png',
            url='/schedule'
        ))


def schedule_update_event(event_id: int, start_timestamp: datetime.datetime, end_timestamp: datetime.datetime, user: User):
    """ Updates an existing event in the schedule. """
    # TODO: Fix testing here
    event = ScheduleEvent.query.filter_by(id=event_id).first()
    if event is None:
        flash('Event not found', category='toast-error')
        db.session.rollback()
        return redirect(request.path)
    if event.user != user:
        flash('You can only edit your own events', category='toast-error')
        return redirect(request.path)
    if event.start_timestamp < pytz.utc.localize(datetime.datetime.now()):
        flash('You cannot edit past events', category='toast-error')
        return redirect(request.path)
    event.start_timestamp = start_timestamp
    event.end_timestamp = end_timestamp
    db.session.commit()

    if event.notification_task:
        event.notification_task.terminate()
        CeleryTask.start_schedule_notification_task(user.id, event.id, start_timestamp, session['timezone'])

    interested_users = User.query.filter(User.roles.any(name='room_owner')).all()
    for interested_user in interested_users:
        send_push_to_user(interested_user, NotificationURL(
            title=f'{user.first_name} rescheduled washing on {start_timestamp.strftime("%d-%m at %H:%M")}.',
            body='Go check the schedule for more details.',
            icon='cycle-reminder-icon.png',
            url='/schedule'
        ))


def schedule_delete_event(event_id: int, user: User):
    """ Deletes an event from the schedule. """
    event = ScheduleEvent.query.filter_by(id=event_id).first()
    if event is None:
        flash('Event not found', category='toast-error')
        return redirect(request.path)
    elif event.user != user and not user.has_role('room_owner'):
        flash('You can only delete your own events', category='toast-error')
        return redirect(request.path)
    else:
        if event.notification_task:
            event.notification_task.terminate()
        db.session.delete(event)
        db.session.commit()

    interested_users = User.query.filter(User.roles.any(name='room_owner')).all()
    for interested_user in interested_users:
        send_push_to_user(interested_user, NotificationURL(
            title=f'{user.first_name} canceled washing on {event.start_timestamp.strftime("%d-%m at %H:%M")}.',
            body='Go check the schedule for more details.',
            icon='cycle-reminder-icon.png',
            url='/schedule'
        ))


def on_washing_machine_notes_limit_breach(request_limit):
    current_app.logger.warning(f'Rate limit breached by {request.remote_addr}. Key: {request_limit.key}')
    flash('Rate limit reached! You can do this action once every 10 minutes!', category='toast-error')
    return redirect(request.path)


@roles_required('admin')
def admin_stop_cycle(user: User):
    cycle: WashingCycle = WashingCycle.query.filter_by(end_timestamp=None).first()
    if not cycle:
        flash('No cycle to stop!', category='toast-warning')
        return redirect(request.path)

    current_app.logger.info(f'Admin {user.username} is stopping the cycle for user {cycle.user.username}.')
    stop_cycle(cycle.user)
    send_push_to_user(cycle.user, Notification(
        title='Cycle stopped by admin',
        body='The admin has stopped your cycle.',
        icon='cycle-reminder-icon.png'
    ))
    flash('Cycle stopped by admin', category='toast-success')


@roles_required('admin')
def admin_start_cycle(user: User):
    current_app.logger.info(f'Admin {user.username} is start a cycle for user {user.username}.')
    start_cycle(user)
    send_push_to_user(user, Notification(
        title='Cycle started by admin',
        body='The admin has started a cycle for you.',
        icon='cycle-reminder-icon.png'
    ))
    flash('Cycle started by admin', category='toast-success')


def record_payment(user: User, amount: decimal.Decimal):
    """ Records a payment for washing cycles by a user. """
    record = WashingCyclePayment(user_id=user.id, amount=amount).propagated
    db.session.add(record)
    db.session.commit()

    interested_users = User.query.filter(User.roles.any(name='room_owner')).all()
    for interested_user in interested_users:
        send_push_to_user(interested_user, Notification(
            title=f'{user.first_name} marked cycles as paid!',
            body=f'They marked cycles for {amount} lv. as paid!',
            icon='paid-cycles-icon.png'
        ))
