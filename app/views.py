import datetime, json
from requests.exceptions import RequestException

from flask import current_app, Blueprint, render_template, request, redirect, session, flash
from flask_security import login_required, user_authenticated, current_user, hash_password, roles_required
from sqlalchemy import or_, and_

from app.db import db
from app.models import *
from app.forms import *

from app.functions import *
from app.statistics import *

views = Blueprint('views', __name__)


@views.before_request
def handle_cycle_buttons():
    # if request is POST, then check if one of the buttons was pressed
    if request.method == 'POST':
        if request.form.get('start_cycle') is not None:
            try:
                start_cycle(current_user)
            except ChildProcessError:
                return redirect(request.path)
            if user_settings.launch_candy_on_cycle_start:
                return redirect(request.path + '?candy=true')
            return redirect(request.path)
        elif request.form.get('stop_cycle') is not None:
            stop_cycle(current_user)
            return redirect(request.path)
        elif request.form.get('release_door') is not None:
            CeleryTask.start_release_door_task()
            flash('Powering the machine for 30 seconds!', category='toast-info')
            return redirect(request.path)


@views.route('/', methods=['GET', 'POST'])
@views.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    cycle_data = update_cycle(current_user)
    statistics = calculate_monthly_statistics(current_user)
    unpaid_cycles = get_unpaid_list(current_user)
    unpaid_cycles_form = UnpaidCyclesForm()

    for _ in range(len(unpaid_cycles)):
        unpaid_cycles_form.checkboxes.append_entry()

    if unpaid_cycles_form.validate_on_submit() and unpaid_cycles_form.unpaid_submit.data:
        if not any([checkbox.data for checkbox in unpaid_cycles_form.checkboxes]):
            flash('Nothing to update', category='toast-warning')
            return redirect(request.path)
        paid_amount = 0
        for checkbox in unpaid_cycles_form.checkboxes:
            if checkbox.data:
                idx = int(checkbox.id.split('-')[1])
                if mark_cycle_paid(current_user, unpaid_cycles[idx].id, True):
                    paid_amount += unpaid_cycles[idx].cost
        flash('Selected cycles marked as paid', category='toast-success')
        room_owner = User.query.filter(User.roles.any(name='room_owner')).first()
        send_push_to_user(room_owner, Notification(
            title=f'{current_user.first_name} marked cycles as paid!',
            body=f'They marked cycles for {paid_amount} lv. as paid!',
            icon='paid-cycles-icon.png'
        ))
        return redirect(request.path)

    expected_end = None
    if cycle_data.get('state', None) == 'running':
        expected_end = (datetime.datetime.now() + datetime.timedelta(minutes=get_remaining_minutes()))

    return render_template(
        'index.html',
        is_dashboard=True,
        cycle_data=cycle_data,
        # stopwatch=get_running_time(),
        expected_end=expected_end,
        total_cost=calculate_charges(current_user),
        total_energy_usage=calculate_energy_usage(current_user),
        unpaid_cycles_cost=calculate_unpaid_cycles_cost(current_user),
        savings=calculate_savings(current_user),
        statistics_labels=json.dumps(statistics['labels']),
        statistics_data=json.dumps(statistics['data']),
        unpaid_cycles=unpaid_cycles,
        unpaid_cycles_form=unpaid_cycles_form
    )


@views.route('/usage/split/<cycle_id>', methods=['GET', 'POST'])
@views.route('/usage', methods=['GET', 'POST'])
@login_required
@roles_required('user')
def usage_view(cycle_id=None):
    mark_paid_form = MarkPaidForm()

    if mark_paid_form.validate_on_submit() and mark_paid_form.mark_paid_submit.data:
        mark_cycle_paid(current_user, mark_paid_form.cycle_id.data)

    other_users = User.query.filter(User.id != current_user.id, User.active).all()
    split_cycle_form = SplitCycleForm()
    split_cycle_form.other_users.choices = [(user.id, user.first_name) for user in other_users]

    if split_cycle_form.validate_on_submit() and split_cycle_form.split_submit.data:
        split_cycle(current_user, split_cycle_form)
        return redirect(request.path)
    elif split_cycle_form.split_submit.data:
        for field, errors in split_cycle_form.errors.items():
            for error in errors:
                flash(f'{error} about {field}', category='toast-error')

    select_form = UsageViewShowCountForm(items=request.args.get('items') or '10')
    if select_form.items.data == 'all':
        limit = None
    else:
        limit = select_form.items.data

    split_request_cycle = None
    if cycle_id is not None:
        cycle = WashingCycle.query.filter_by(id=cycle_id).first()
        split = WashingCycleSplit.query.filter_by(cycle_id=cycle_id, user_id=current_user.id).first()
        if cycle is None:
            flash('Cycle not found', category='toast-error')
            return redirect('/usage')
        elif not split:
            flash('Split wasn\'t found', category='toast-error')
            return redirect('/usage')
        elif split.accepted:
            flash('Split already accepted', category='toast-error')
            return redirect('/usage')
        else:
            split_request_cycle = cycle
            split_users_count = len(cycle.splits)
            cycle.split_cost = round(cycle.cost / (split_users_count + 1), 2)
            if cycle.split_cost * (split_users_count + 1) < cycle.cost:
                cycle.split_cost = round(cycle.split_cost + decimal.Decimal(0.01), 2)

    return render_template(
        'usage.html',
        is_usage=True,
        cycle_data=update_cycle(current_user),
        select_form=select_form,
        usages=get_usage_list(current_user, limit),
        split_cycle_form=split_cycle_form,
        mark_paid_form=mark_paid_form,
        split_request_cycle=split_request_cycle
    )


@views.route('/usage/split/<cycle_id>/<action>', methods=['GET', 'POST'])
@login_required
@roles_required('user')
def split_cycle_actions(cycle_id, action=None):
    cycle = WashingCycle.query.filter_by(id=cycle_id).first()
    split = WashingCycleSplit.query.filter_by(cycle_id=cycle_id, user_id=current_user.id).first()
    if cycle is None:
        flash('Cycle not found', category='toast-error')
    elif not split:
        flash('You aren\'t associated with this cycle', category='toast-error')
    elif split.accepted:
        flash('You can\'t use this action on this cycle', category='toast-error')
    else:
        if action == 'accept':
            split.accepted = True
            db.session.commit()
            flash('Cycle split accepted', category='toast-success')
        elif action == 'reject':
            db.session.delete(split)
            db.session.commit()
            flash('Cycle split rejected', category='toast-success')
        else:
            flash('Action not recognized', category='toast-error')
    return redirect('/usage')


@views.route('/schedule', methods=['GET', 'POST'])
@login_required
@roles_required('user')
def schedule():
    schedule_request_form = ScheduleEventRequestForm()

    if schedule_request_form.validate_on_submit() and schedule_request_form.event_submit.data:
        # first calculate timestamps and check for correctness
        start_timestamp = schedule_request_form.start_timestamp.data
        duration = 0
        if schedule_request_form.cycle_type.data == 'both':
            duration = float(os.getenv('SCHEDULE_WASH_DRY_DURATION', 4.5))
        elif schedule_request_form.cycle_type.data == 'wash':
            duration = float(os.getenv('SCHEDULE_WASH_DURATION', 1.5))
        elif schedule_request_form.cycle_type.data == 'dry':
            duration = float(os.getenv('SCHEDULE_DRY_DURATION', 3.5))

        end_timestamp = start_timestamp + datetime.timedelta(hours=duration)

        if schedule_check_for_overlapping(start_timestamp, end_timestamp, schedule_request_form.id.data):
            # the timeslot collides with another event
            flash('Timeslot is already reserved! Please request another one!', category='toast-warning')
        else:
            if schedule_request_form.id.data:
                # editing an existing event and updating notification task
                schedule_update_event(schedule_request_form.id.data, start_timestamp, end_timestamp, current_user)
                flash('Event updated successfully', category='toast-success')
            else:
                # creating a new event and task for notification
                schedule_create_new_event(start_timestamp, end_timestamp, current_user)
                flash('Event created successfully', category='toast-success')
        return redirect(request.path)
    elif schedule_request_form.event_submit.data:
        for field, errors in schedule_request_form.errors.items():
            for error in errors:
                flash(error, category='toast-error')

    if request.args.get('delete'):
        # deleting event if delete parameter is present in URL
        schedule_delete_event(int(request.args.get('delete')), current_user)
        flash('Event deleted successfully', category='toast-success')
        return redirect(request.path)

    # get events for current week
    today = datetime.datetime.now().date()
    navigation = ScheduleNavigationForm()

    if navigation.validate_on_submit() and (navigation.previous.data or navigation.next.data or navigation.today.data):
        if navigation.previous.data:
            today = navigation.date.data - datetime.timedelta(days=7)
        elif navigation.next.data:
            today = navigation.date.data + datetime.timedelta(days=7)
        elif navigation.today.data:
            today = datetime.datetime.now().date()

    day_of_week = today.weekday()

    events = ScheduleEvent.query.filter(
        ScheduleEvent.start_timestamp >= today - datetime.timedelta(days=day_of_week),
        ScheduleEvent.start_timestamp <= today + datetime.timedelta(days=7 - day_of_week),
    ).all()

    events_json = []
    for event in events:
        events_json.append({
            'id': event.id,
            'start_date': event.start_timestamp.strftime('%Y-%m-%d %H:%M'),
            'end_date': event.end_timestamp.strftime('%Y-%m-%d %H:%M'),
            'text': f'Timeslot {event.start_timestamp.strftime("%Y-%m-%d %H:%M")} - '
                    f'{event.end_timestamp.strftime("%Y-%m-%d %H:%M")} reserved by {event.user.first_name} on '
                    f'{event.timestamp.strftime("%Y-%m-%d %H:%M")}',
            'color': '7fc2d1'
        })

    return render_template(
        'schedule.html',
        is_schedule=True,
        cycle_data=update_cycle(current_user),
        today=today,
        navigation=navigation,
        schedule_requests=json.dumps(events_json),
        schedule_request_form=schedule_request_form
    )


@views.route('/profile', methods=['GET', 'POST'])
@login_required
@roles_required('user')
def profile():
    edit_form = EditProfileForm()
    settings_form = EditSettingsForm()

    if edit_form.validate_on_submit() and edit_form.profile_submit.data:
        if not edit_form.first_name.data and not edit_form.email.data and not edit_form.username.data and \
                not edit_form.password.data:
            flash('Nothing to update', category='profile')
        else:
            if edit_form.first_name.data:
                current_user.first_name = edit_form.first_name.data
            if edit_form.email.data:
                current_user.email = edit_form.email.data
            if edit_form.username.data:
                current_user.username = edit_form.username.data
            if edit_form.password.data:
                current_user.password = hash_password(edit_form.password.data)

            db.session.commit()
            flash('Profile updated successfully', 'success')
        return redirect(request.path)

    user_settings = UserSettings.query.filter_by(user_id=current_user.id).first()
    if settings_form.validate_on_submit() and settings_form.settings_submit.data:
        user_settings.terminate_cycle_on_usage = settings_form.automatic_stop.data
        user_settings.launch_candy_on_cycle_start = settings_form.automatic_open_candy.data
        db.session.commit()
    else:
        settings_form.automatic_stop.data = user_settings.terminate_cycle_on_usage
        settings_form.automatic_open_candy.data = user_settings.launch_candy_on_cycle_start

    return render_template(
        'profile.html',
        is_profile=True,
        cycle_data=update_cycle(current_user),
        edit_form=edit_form,
        settings_form=settings_form
    )


@views.route('/washing-machine', methods=['GET', 'POST'])
@login_required
@roles_required('user')
def washing_machine():
    try:
        washing_machine_info = get_washer_info()
    except RequestException:
        washing_machine_info = {
            'relay_ison': None,
            'running_time': None,
            'current_usage': None,
            'relay_temperature': None,
            'relay_wifi_rssi': None,
        }

    return render_template(
        'washing-machine.html',
        is_washer=True,
        cycle_data=update_cycle(current_user),
        stopwatch=washing_machine_info['running_time'],
        current_usage=washing_machine_info['current_usage'],
        relay_temperature=washing_machine_info['relay_temperature'],
        relay_wifi_rssi=washing_machine_info['relay_wifi_rssi'],
        candy_user=os.getenv('CANDY_USER'),
        candy_password=os.getenv('CANDY_PASSWORD')
    )
