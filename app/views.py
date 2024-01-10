import datetime, json

from flask import current_app, Blueprint, render_template, request, redirect, session, flash
from flask_security import login_required, user_authenticated, current_user, hash_password, roles_required
from sqlalchemy import or_, and_

from app.db import db
from app.models import *
from app.forms import *

from app.functions import *
from app.statistics import *
from app.tasks import schedule_notification, release_door


views = Blueprint('views', __name__)


@views.before_request
def handle_cycle_buttons():
    # if request is POST, then check if one of the buttons was pressed
    if request.method == 'POST':
        if request.form.get('start_cycle') is not None:
            user_settings = UserSettings.query.filter_by(user_id=current_user.id).first()
            try:
                start_cycle(current_user, user_settings)
            except ChildProcessError:
                return redirect(request.path)
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
                if unpaid_cycles[idx].split_users:
                    db.session.query(split_cycles).filter_by(
                        cycle_id=unpaid_cycles[idx].id, user_id=current_user.id
                    ).update({split_cycles.c.paid: True})
                else:
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
    mark_paid_form = MarkPaidForm()

    if mark_paid_form.validate_on_submit() and mark_paid_form.cycle_id.data:
        cycle = WashingCycle.query.filter_by(id=mark_paid_form.cycle_id.data).first()
        if cycle is None:
            flash('Cycle not found', category='toast-error')
        elif cycle.user_id != current_user.id:
            flash('You can only mark your own cycles as paid', category='toast-error')
        elif cycle.paid:
            flash('Cycle already marked as paid', category='toast-error')
        else:
            cycle.paid = True
            db.session.commit()
            flash('Cycle marked as paid', category='toast-success')

    other_users = User.query.filter(User.id != current_user.id, User.active).all()
    split_cycle_form = SplitCycleForm()
    split_cycle_form.other_users.choices = [(user.id, user.first_name) for user in other_users]

    if split_cycle_form.validate_on_submit() and split_cycle_form.submit.data:
        cycle: WashingCycle = WashingCycle.query.filter_by(id=split_cycle_form.cycle_id.data).first()
        if cycle.user_id != current_user.id:
            flash('You can only split your own cycles', category='toast-error')
        elif cycle.paid:
            flash('You cannot split paid cycles', category='toast-error')
        else:
            if cycle.split_users:
                splits = db.session.query(split_cycles).filter_by(cycle_id=cycle.id).all()
                for split in splits:
                    if split.paid:
                        flash('You cannot split cycles that are partially paid', category='toast-error')
                        return redirect(request.path)
            for user_id in split_cycle_form.other_users.data:
                cycle.split_users.append(User.query.filter_by(id=user_id).first())
            db.session.commit()
            flash('Cycle split successfully', category='toast-success')
        return redirect(request.path)
    else:
        for field, errors in split_cycle_form.errors.items():
            for error in errors:
                flash(error, category='toast-error')

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
        usages=get_usage_list(current_user, limit),
        split_cycle_form=split_cycle_form,
        mark_paid_form=mark_paid_form
    )


@views.route('/schedule', methods=['GET', 'POST'])
@login_required
@roles_required('user')
def schedule():
    schedule_request_form = ScheduleEventRequestForm()

    if schedule_request_form.validate_on_submit() and schedule_request_form.submit.data:
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

        overlapping_events = ScheduleEvent.query.filter(
            ScheduleEvent.id != schedule_request_form.id.data,
            or_(and_(start_timestamp >= ScheduleEvent.start_timestamp,
                     start_timestamp <= ScheduleEvent.end_timestamp),
                and_(end_timestamp >= ScheduleEvent.start_timestamp,
                     end_timestamp <= ScheduleEvent.end_timestamp)
                )).all()

        if overlapping_events:
            # the timeslot collides with another event
            flash('Timeslot is already reserved! Please request another one!', category='toast-warning')
        else:
            if schedule_request_form.id.data:
                # editing an existing event and updating notification task
                event = ScheduleEvent.query.filter_by(id=schedule_request_form.id.data).first()
                if event is None:
                    flash('Event not found', category='toast-error')
                    db.session.rollback()
                    return redirect(request.path)
                if event.user != current_user:
                    flash('You can only edit your own events', category='toast-error')
                    return redirect(request.path)
                event.start_timestamp = start_timestamp
                event.end_timestamp = end_timestamp
                if event.notification_task_id:
                    AsyncResult(event.notification_task_id).revoke(terminate=True)
                    notification_task_id = schedule_notification.apply_async(
                        (current_user.id,),
                        eta=start_timestamp - datetime.timedelta(minutes=int(os.getenv('SCHEDULE_REMINDER_DELTA', 5)))
                    ).id
                    event.notification_task_id = notification_task_id
            else:
                # creating a new event and task for notification
                notification_task_id = schedule_notification.apply_async(
                    (current_user.id,),
                    eta=start_timestamp - datetime.timedelta(minutes=int(os.getenv('SCHEDULE_REMINDER_DELTA', 5)))
                ).id
                event = ScheduleEvent(
                    start_timestamp=start_timestamp,
                    end_timestamp=end_timestamp,
                    user_id=current_user.id,
                    notification_task_id=notification_task_id
                )
                db.session.add(event)
            db.session.commit()
        return redirect(request.path)
    elif schedule_request_form.submit.data:
        for field, errors in schedule_request_form.errors.items():
            for error in errors:
                flash(error, category='toast-error')

    if request.args.get('delete'):
        # deleting event if delete parameter is present in URL
        event = ScheduleEvent.query.filter_by(id=request.args.get('delete')).first()
        if event is None:
            flash('Event not found', category='toast-error')
        elif event.user != current_user and not current_user.has_role('room_owner'):
            flash('You can only delete your own events', category='toast-error')
        else:
            db.session.delete(event)
            db.session.commit()
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

    if edit_form.validate_on_submit() and edit_form.submit.data:
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
    if settings_form.validate_on_submit() and settings_form.submit.data:
        # print('New setting is {}'.format(settings_form.automatic_stop.data))
        user_settings.terminate_cycle_on_usage = settings_form.automatic_stop.data
        user_settings.launch_candy_on_cycle_start = settings_form.automaitc_open_candy.data
        db.session.commit()
    else:
        settings_form.automatic_stop.data = user_settings.terminate_cycle_on_usage
        settings_form.automaitc_open_candy.data = user_settings.launch_candy_on_cycle_start

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
