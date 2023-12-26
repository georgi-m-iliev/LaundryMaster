import datetime, json

from flask import current_app, Blueprint, render_template, request, redirect, session, flash
from flask_security import login_required, user_authenticated, current_user, hash_password, roles_required
from sqlalchemy import or_, and_

from app.db import db
from app.models import (User, WashingCycle, UsageViewShowCountForm, EditProfileForm, LoginForm, UnpaidCyclesForm,
                        UserSettings, EditSettingsForm, ScheduleEvent, ScheduleEventRequestForm)

from app.functions import *
from app.tasks import watch_usage_and_notify_cycle_end, release_door


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
            WashingMachine.query.first().notification_task_id = watch_usage_and_notify_cycle_end.delay(
                current_user.id,
                UserSettings.query.filter_by(user_id=current_user.id).first().terminate_cycle_on_usage
            ).id
            db.session.commit()

            user_settings = UserSettings.query.filter_by(user_id=current_user.id).first()
            if user_settings.launch_candy_on_cycle_start:
                return redirect(request.path + '?candy=true')

            return redirect(request.path)
        elif request.form.get('stop_cycle') is not None:
            stop_cycle(current_user)
            return redirect(request.path)
        elif request.form.get('release_door') is not None:
            release_door.delay(current_user.username)
            flash('Powering the machine for 30 seconds!', category='toast-info')
            return redirect(request.path)


@views.route('/', methods=['GET', 'POST'])
@views.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    statistics = calculate_monthly_statistics(current_user)
    unpaid_cycles = get_unpaid_list(current_user)
    unpaid_cycles_form = UnpaidCyclesForm()

    for _ in range(len(unpaid_cycles)):
        unpaid_cycles_form.checkboxes.append_entry()

    if request.form.get('unpaid-submit') is not None and unpaid_cycles_form.validate_on_submit():
        for checkbox in unpaid_cycles_form.checkboxes:
            if checkbox.data:
                idx = int(checkbox.id.split('-')[1])
                unpaid_cycles[idx].paid = True
                db.session.commit()
        flash('Selected cycles were marked as paid', 'toast-success')
        return redirect(request.path)

    return render_template(
        'index.html',
        is_dashboard=True,
        cycle_data=update_cycle(current_user),
        stopwatch=get_running_time(),
        total_cost=calculate_charges(current_user),
        total_usage=calculate_usage(current_user),
        unpaid_cycles_cost=calculate_unpaid_cycles_cost(current_user),
        savings=calculate_savings(current_user),
        monthly_statistics=calculate_monthly_statistics(current_user),
        statistics_labels=json.dumps(statistics['labels']),
        statistics_data=json.dumps(statistics['data']),
        unpaid_cycles=unpaid_cycles,
        unpaid_cycles_form=unpaid_cycles_form
    )


@views.route('/usage', methods=['GET', 'POST'])
@login_required
@roles_required('user')
def usage_view():
    select_form = UsageViewShowCountForm(items=request.args.get('items') or '10')

    if select_form.items.data == 'all':
        limit = None
    else:
        limit = select_form.items.data

    return render_template(
        'usage.html',
        is_usage=True,
        cycle_data=update_cycle(current_user),
        select_form=select_form,
        usages=get_usage_list(current_user, limit)
    )


@views.route('/schedule', methods=['GET', 'POST'])
@login_required
@roles_required('user')
def schedule():
    schedule_request_form = ScheduleEventRequestForm()

    if schedule_request_form.validate_on_submit():
        start_timestamp = schedule_request_form.start_timestamp.data
        duration = 0
        if schedule_request_form.cycle_type.data == 'both':
            duration = float(os.getenv('SCHEDULE_WASH_DRY_DURATION', 4.5))
        elif schedule_request_form.cycle_type.data == 'wash':
            duration = float(os.getenv('SCHEDULE_WASH_DURATION', 1.5))
        elif schedule_request_form.cycle_type.data == 'dry':
            duration = float(os.getenv('SCHEDULE_DRY_DURATION', 3.5))

        new_event = ScheduleEvent(
            start_timestamp=start_timestamp,
            end_timestamp=start_timestamp + datetime.timedelta(hours=duration),
            user_id=current_user.id
        )
        # overlapping_events_start = ScheduleEvent.query.filter(
        #     new_event.start_timestamp >= ScheduleEvent.start_timestamp,
        #     new_event.start_timestamp <= ScheduleEvent.end_timestamp
        # ).all()
        # overlapping_events_end = ScheduleEvent.query.filter(
        #     new_event.end_timestamp >= ScheduleEvent.start_timestamp,
        #     new_event.end_timestamp <= ScheduleEvent.end_timestamp
        # ).all()
        #
        # overlapping_events = overlapping_events_start + overlapping_events_end
        overlapping_events = ScheduleEvent.query.filter(
            or_(and_(new_event.start_timestamp >= ScheduleEvent.start_timestamp,
                     new_event.start_timestamp <= ScheduleEvent.end_timestamp),
                and_(new_event.end_timestamp >= ScheduleEvent.start_timestamp,
                     new_event.end_timestamp <= ScheduleEvent.end_timestamp))).all()
        if overlapping_events:
            flash('Timeslot is already reserved! Please request another one!', category='toast-warning')
        else:
            db.session.add(new_event)
            db.session.commit()

        return redirect(request.path)
    else:
        for field, errors in schedule_request_form.errors.items():
            for error in errors:
                flash(error, category='toast-error')

    if request.args.get('delete'):
        # deleting event if delete parameter is present in URL
        event = ScheduleEvent.query.filter_by(id=request.args.get('delete')).first()
        if event.user != current_user:
            flash('You can only delete your own events', category='toast-error')
        else:
            db.session.delete(event)
            db.session.commit()
        return redirect(request.path)

    # get events for current week
    day_of_week = datetime.datetime.today().weekday()

    events = ScheduleEvent.query.filter(
        ScheduleEvent.start_timestamp >= datetime.datetime.now().date() - datetime.timedelta(days=day_of_week),
        ScheduleEvent.start_timestamp <= datetime.datetime.now().date() + datetime.timedelta(days=7 - day_of_week),
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
        schedule_requests=json.dumps(events_json),
        schedule_request_form=schedule_request_form
    )


@views.route('/profile', methods=['GET', 'POST'])
@login_required
@roles_required('user')
def profile():
    edit_form = EditProfileForm()
    settings_form = EditSettingsForm()

    if 'profile-submit' in request.form and edit_form.validate_on_submit():
        if True not in (
            edit_form.first_name.data, edit_form.email.data, edit_form.username.data, edit_form.password.data
        ):
            flash('Nothing to update', category='profile')
            return redirect(request.path)

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
    if 'settings-submit' in request.form and settings_form.validate_on_submit():
        # print('New setting is {}'.format(settings_form.automatic_stop.data))
        user_settings.terminate_cycle_on_usage = settings_form.automatic_stop.data
        user_settings.launch_candy_on_cycle_start = settings_form.automaitc_open_candy.data
        db.session.commit()
    else:
        settings_form.automatic_stop.data = user_settings.terminate_cycle_on_usage

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

    washing_machine_info = get_washer_info()

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
