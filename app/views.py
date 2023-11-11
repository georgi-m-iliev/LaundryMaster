import datetime, json

from flask import current_app, Blueprint, render_template, request, redirect, session, flash
from flask_security import login_required, user_authenticated, current_user, hash_password

from app.db import db
from app.models import User, WashingCycle, UsageViewShowCountForm, EditProfileForm, LoginForm, UnpaidCyclesForm, UserSettings, EditSettingsForm
from app.functions import *
from app.tasks import watch_usage_and_notify_cycle_end, release_door


views = Blueprint('views', __name__)


@views.before_request
def handle_cycle_buttons():
    # if request is POST, then check if one of the buttons was pressed
    if request.method == 'POST':
        if request.form.get('start_cycle') is not None:
            start_cycle(current_user)
            WashingMachine.query.first().notification_task_id = watch_usage_and_notify_cycle_end.delay(
                current_user.id,
                UserSettings.query.filter_by(user_id=current_user.id).first().terminate_cycle_on_usage
            ).id
            db.session.commit()
        elif request.form.get('stop_cycle') is not None:
            stop_cycle(current_user)
        elif request.form.get('release_door') is not None:
            release_door.delay(current_user.username)
            flash('Powering the machine for 30 seconds!', category='toast-info')

        else:
            pass
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

    if unpaid_cycles_form.validate_on_submit():
        for checkbox in unpaid_cycles_form.checkboxes:
            if checkbox.data:
                idx = int(checkbox.id.split('-')[1])
                unpaid_cycles[idx].paid = True
                db.session.commit()
        # flash('Selected cycles were marked as paid', 'success')
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


@views.route('/profile', methods=['GET', 'POST'])
@login_required
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
        print('New setting is {}'.format(settings_form.automatic_stop.data))
        user_settings.terminate_cycle_on_usage = settings_form.automatic_stop.data
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
def washing_machine():

    return render_template(
        'washing-machine.html',
        is_washer=True,
        cycle_data=update_cycle(current_user),
        stopwatch=get_running_time(),
        current_usage=get_realtime_current_usage(),
        candy_user=os.getenv('CANDY_USER'),
        candy_password=os.getenv('CANDY_PASSWORD')
    )
