import os, datetime

from app import db

from flask_security import UserMixin, RoleMixin
from sqlalchemy import func

from flask_wtf import FlaskForm
from wtforms import ValidationError
from wtforms import (StringField, PasswordField, SubmitField, SelectField,
                     BooleanField, FieldList, DateTimeLocalField, SelectMultipleField)
from wtforms.validators import DataRequired, Length, Email, EqualTo, Optional

roles_users = db.Table(
    'roles_users',
    db.Column('user_id', db.Integer(), db.ForeignKey('users.id')),
    db.Column('role_id', db.Integer(), db.ForeignKey('roles.id'))
)


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(128), unique=True)
    username = db.Column(db.String(128), unique=True)
    password = db.Column(db.String(512))
    first_name = db.Column(db.String(150))
    active = db.Column(db.Boolean())
    last_login = db.Column(db.DateTime(timezone=True))
    fs_uniquifier = db.Column(db.String(64), unique=True)
    roles = db.relationship('Role', secondary='roles_users', backref=db.backref('users', lazy='dynamic'))


class Role(db.Model, RoleMixin):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True)
    description = db.Column(db.String(512))


class UserSettings(db.Model):
    __tablename__ = 'user_settings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    terminate_cycle_on_usage = db.Column(db.Boolean(), default=False)
    launch_candy_on_cycle_start = db.Column(db.Boolean(), default=True)


class WashingCycle(db.Model):
    __tablename__ = 'washing_cycles'
    id = db.Column(db.Integer, primary_key=True)
    startkwh = db.Column(db.Numeric(20, 4))
    endkwh = db.Column(db.Numeric(20, 4))
    cost = db.Column(db.Numeric(10, 2))
    start_timestamp = db.Column(db.DateTime(timezone=True), default=func.now())
    end_timestamp = db.Column(db.DateTime(timezone=True))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user = db.relationship('User', backref=db.backref('washing_cycles', lazy=True))
    paid = db.Column(db.Boolean(), default=False)


class WashingMachine(db.Model):
    __tablename__ = 'washing_machine'
    id = db.Column(db.Integer, primary_key=True)
    currentkwh = db.Column(db.Numeric(20, 4))
    costperkwh = db.Column(db.Numeric(10, 2))
    public_wash_cost = db.Column(db.Numeric(10, 2))
    notification_task_id = db.Column(db.String(512))


class LoginForm(FlaskForm):
    username = StringField('username', validators=[DataRequired()])
    password = PasswordField('password',
                             validators=[DataRequired(), Length(min=6, max=128)],
                             render_kw={'type': 'password'}
                             )
    login = SubmitField('login')


class RequestPasswordResetForm(FlaskForm):
    email = StringField('email', validators=[DataRequired(), Email()])
    submit = SubmitField('Send email')


class PasswordResetForm(FlaskForm):
    password = PasswordField('password', validators=[Length(min=6, max=128)])
    password_confirm = PasswordField('password_again',
                                     validators=[
                                         Length(min=6, max=128),
                                         EqualTo('password', message="Passwords don't match"),
                                     ])
    submit = SubmitField('Save password')


class EditProfileForm(FlaskForm):
    first_name = StringField('first_name', validators=[Optional()])
    email = StringField('email', validators=[Email(), Optional()])
    username = StringField('username', validators=[Optional()])
    password = PasswordField('password', validators=[Length(min=6, max=128), Optional()])
    password_confirm = PasswordField('password_again',
                                     validators=[
                                         Length(min=6, max=128),
                                         EqualTo('password', message="Passwords don't match"),
                                         Optional()
                                     ])
    submit = SubmitField('Save Changes', id='profile-submit', name='profile-submit')


class EditSettingsForm(FlaskForm):
    automatic_stop = BooleanField(default=False)
    automaitc_open_candy = BooleanField(default=True)
    submit = SubmitField('', id='settings-submit', name='settings-submit')


class EditRolesForm(FlaskForm):
    roles_to_add = SelectMultipleField('roles_to_add', choices=[])
    roles_to_remove = SelectMultipleField('roles_to_remove', choices=[])
    submit = SubmitField('submit', id='roles-submit', name='roles-submit')


class UsageViewShowCountForm(FlaskForm):
    items = SelectField('ShowCount', choices=[(10, '10'), (20, '20'), (50, '50'), (100, '100'), ('all', 'All')])


class UnpaidCyclesForm(FlaskForm):
    checkboxes = FieldList(BooleanField('checkboxes', default=False, validators=[Optional()]), min_entries=0)
    submit = SubmitField('submit')


class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True, unique=True)
    subscription_json = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))


class ScheduleEvent(db.Model):
    __tablename__ = 'schedule'
    id = db.Column(db.Integer, primary_key=True, unique=True)
    timestamp = db.Column(db.DateTime(timezone=True), default=func.now())
    start_timestamp = db.Column(db.DateTime(timezone=True))
    end_timestamp = db.Column(db.DateTime(timezone=True))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user = db.relationship('User', backref=db.backref('schedule_events', lazy=True))


class ScheduleEventRequestForm(FlaskForm):
    start_timestamp = DateTimeLocalField('start_timestamp', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    cycle_type = SelectField(
        'cycle_type',
        choices=[('both', 'Washing & Drying'), ('wash', 'Washing'), ('dry', 'Drying')]
    )
    submit = SubmitField('submit')

    def validate_start_timestamp(self, field):
        if field.data < datetime.datetime.now():
            raise ValidationError('Start time must be in the future!')
        start_hour = int(os.getenv('SCHEDULE_MIN_HOUR', 8))
        end_hour = int(os.getenv('SCHEDULE_MAX_HOUR', 23))
        if field.data.hour < start_hour or field.data.hour > end_hour:
            raise ValidationError(f'Start time must be between {start_hour} and {end_hour}')
