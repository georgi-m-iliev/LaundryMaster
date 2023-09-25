import datetime, json

from flask import Blueprint, render_template, request, redirect, session, flash
from flask_security import login_required, user_authenticated, current_user, hash_password

from app.db import db
from app.models import User, WashingCycle, UsageViewShowCountForm, EditProfileForm, LoginForm
from app.functions import *

views = Blueprint('views', __name__)


@views.before_request
def handle_cycle_buttons():
    # if request is POST, then check if one of the buttons was pressed
    if request.method == 'POST':
        if request.form.get('start_cycle') is not None:
            start_cycle(current_user)
            return redirect(request.path)
        elif request.form.get('stop_cycle') is not None:
            stop_cycle(current_user)
            return redirect(request.path)
        else:
           pass

    # if request wasn't POST, then update the cycle information, to display proper buttons
    if current_user.is_authenticated:
        update_cycle(current_user)


@views.route('/', methods=['GET', 'POST'])
@views.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    statistics = calculate_monthly_statistics(current_user)

    return render_template(
        'index.html',
        is_dashboard=True,
        total_cost=calculate_charges(current_user),
        total_usage=calculate_usage(current_user),
        unpaid_cycles_cost=calculate_unpaid_cycles_cost(current_user),
        stopwatch=calculate_running_time(current_user),
        monthly_statistics=calculate_monthly_statistics(current_user),
        statistics_labels=json.dumps(statistics['labels']),
        statistics_data=json.dumps(statistics['data']),
        unpaid_cycles=get_unpaid_list(current_user)
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
        select_form=select_form,
        usages=get_usage_list(current_user, limit)
    )


@views.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    edit_form = EditProfileForm()
    if edit_form.validate_on_submit():
        if not edit_form.first_name.data and not edit_form.email.data and not edit_form.username.data and not edit_form.password.data:
            flash('Nothing to update', 'warning')
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

    return render_template(
        'profile.html',
        is_profile=True,
        edit_form=edit_form
    )
