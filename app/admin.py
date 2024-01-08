import datetime, json
from flask import Blueprint, request, render_template, redirect, flash
from flask_security import roles_required, hash_password, current_user

from app.db import db
from app.auth import user_datastore
from app.models import User, Role, WashingCycle, ScheduleEvent, UserSettings
from app.forms import EditProfileForm, EditRolesForm
from app.statistics import calculate_unpaid_cycles_cost
from app.functions import delete_user

admin = Blueprint('admin', __name__)


@admin.route('/', methods=['GET'])
@roles_required('admin')
def index():
    return render_template(
        'admin/index.html',
        is_dashboard=True,
        unpaid_cycles_cost=calculate_unpaid_cycles_cost()
    )


@admin.route('/users', methods=['GET', 'POST'])
@roles_required('admin')
def users_view():
    if 'delete' in request.args or 'activate' in request.args or 'deactivate' in request.args:
        if request.args.get('delete'):
            user_id = request.args.get('delete')
            user = User.query.filter_by(id=user_id).first()
            if user is None:
                flash(f'User does not exist', category='toast-error')
                return redirect(request.path)
            if user == current_user:
                flash(f'You cannot delete yourself', category='toast-error')
                return redirect(request.path)
            delete_user(user)
            flash(f'Deleted user {user.username}', category='toast-success')
        elif request.args.get('activate'):
            user_id = request.args.get('activate')
            user = User.query.filter_by(id=user_id).first()
            if user is None:
                flash(f'User does not exist', category='toast-error')
                return redirect(request.path)
            user_datastore.activate_user(user)
            flash(f'Activated user {user.username}', category='toast-success')
        elif request.args.get('deactivate'):
            user_id = request.args.get('deactivate')
            user = User.query.filter_by(id=user_id).first()
            if user is None:
                flash(f'User does not exist', category='toast-error')
                return redirect(request.path)
            user_datastore.deactivate_user(user)
            flash(f'Deactivated user {user.username}', category='toast-success')
        db.session.commit()
        return redirect(request.path)

    users = User.query.order_by(User.id).all()
    edit_user_form = EditProfileForm()
    edit_roles_form = EditRolesForm()

    roles = []
    for role in Role.query.all():
        roles.append(role.name)

    edit_roles_form.roles_to_add.choices = [(role, role.replace('_', ' ').title()) for role in roles]
    edit_roles_form.roles_to_remove.choices = [(role, role.replace('_', ' ').title()) for role in roles]

    roles = ', '.join([role.replace('_', ' ') for role in roles])

    if edit_user_form.validate_on_submit() and edit_user_form.submit.data:
        if request.args.get('user_id'):
            # print('Profile update...')
            user = User.query.filter_by(id=request.args.get('user_id')).first()
            if user is None:
                flash('User not found.', category='toast-error')
                return redirect(request.path)

            if ('', '', '', '') == (edit_user_form.first_name.data, edit_user_form.email.data,
                                    edit_user_form.username.data, edit_user_form.password.data):
                flash('Nothing to update.', category='toast-info')
                return redirect(request.path)
            else:
                if edit_user_form.first_name.data:
                    user.first_name = edit_user_form.first_name.data
                if edit_user_form.email.data:
                    user.email = edit_user_form.email.data
                if edit_user_form.username.data:
                    user.username = edit_user_form.username.data
                if edit_user_form.password.data:
                    user.password = hash_password(edit_user_form.password.data)
                flash('User updated successfully', 'toast-success')
        else:
            # print('Creating new user...')
            user_datastore.create_user(
                first_name=edit_user_form.first_name.data,
                email=edit_user_form.email.data,
                username=edit_user_form.username.data,
                password=hash_password(edit_user_form.password.data)
            )
            settings = UserSettings(user_id=User.query.filter_by(username=edit_user_form.username.data).first().id)
            db.session.add(settings)
            flash('User created successfully', 'toast-success')
        db.session.commit()
        return redirect(request.path)
    else:
        for field, errors in edit_user_form.errors.items():
            for error in errors:
                flash(error, category='toast-error')

    if request.args.get('user_id') and edit_roles_form.validate_on_submit() and edit_roles_form.submit.data:
        # print('Changing roles...')
        user = User.query.filter_by(id=request.args.get('user_id')).first()
        if user:
            for role in edit_roles_form.roles_to_add.data:
                user_datastore.add_role_to_user(user, role)
            for role in edit_roles_form.roles_to_remove.data:
                user_datastore.remove_role_from_user(user, role)
            db.session.commit()
            flash('Roles updated successfully', 'toast-success')
        else:
            flash(f'User does not exist', category='toast-error')
        return redirect(request.path)
    else:
        for field, errors in edit_roles_form.errors.items():
            for error in errors:
                flash(error, category='toast-error')

    return render_template(
        'admin/users.html',
        is_users=True,
        users=users,
        edit_user_form=edit_user_form,
        roles=roles,
        edit_roles_form=edit_roles_form
    )


@admin.route('/cycles', methods=['GET'])
@roles_required('admin')
def cycles_view():
    cycles = WashingCycle.query.order_by(WashingCycle.start_timestamp.desc()).limit(1000).all()
    for cycle in cycles:
        cycle.start_timestamp_formatted = cycle.start_timestamp.strftime("%d-%m-%Y %H:%M:%S")
        if cycle.end_timestamp:
            cycle.end_timestamp_formatted = cycle.end_timestamp.strftime("%d-%m-%Y %H:%M:%S")
            cycle.duration = str(cycle.end_timestamp - cycle.start_timestamp).split('.')[0]

    return render_template(
        'admin/cycles.html',
        is_cycles=True,
        cycles=cycles
    )


@admin.route('/schedule', methods=['GET'])
@roles_required('admin')
def schedule_view():
    current_date = datetime.datetime.now()
    start_date = datetime.datetime(year=current_date.year, month=current_date.month, day=1)
    events = ScheduleEvent.query.filter(
        ScheduleEvent.start_timestamp >= start_date,
        ScheduleEvent.start_timestamp <= start_date + datetime.timedelta(days=31)
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
        'admin/schedule.html',
        is_schedule=True,
        schedule_requests=json.dumps(events_json)
    )
