import os
import datetime

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectMultipleField, SelectField, FieldList
from wtforms import IntegerField, DateTimeLocalField, ValidationError, DateField
from wtforms.validators import DataRequired, Length, Email, EqualTo, Optional


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


class ScheduleEventRequestForm(FlaskForm):
    id = IntegerField('id', validators=[Optional()])
    start_timestamp = DateTimeLocalField('start_timestamp', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    cycle_type = SelectField(
        'cycle_type',
        choices=[('both', 'Washing & Drying'), ('wash', 'Washing'), ('dry', 'Drying')]
    )
    submit = SubmitField('submit')

    @staticmethod
    def validate_start_timestamp(self, field):
        if field.data < datetime.datetime.now():
            raise ValidationError('Start time must be in the future!')
        start_hour = int(os.getenv('SCHEDULE_MIN_HOUR', 8))
        end_hour = int(os.getenv('SCHEDULE_MAX_HOUR', 23))
        if field.data.hour < start_hour or field.data.hour > end_hour:
            raise ValidationError(f'Start time must be between {start_hour} and {end_hour}')


class ScheduleNavigationForm(FlaskForm):
    date = DateField('date', format='%Y-%m-%d', validators=[DataRequired()])
    next = SubmitField('next', id='next', name='next')
    today = SubmitField('today', id='today', name='today')
    previous = SubmitField('previous', id='previous', name='previous')


class SplitCycleForm(FlaskForm):
    other_users = SelectMultipleField('other_users', choices=[], coerce=int)
    cycle_id = IntegerField('cycle_id', validators=[DataRequired()])
    submit = SubmitField('submit')


class MarkPaidForm(FlaskForm):
    cycle_id = IntegerField('cycle_id', validators=[DataRequired()])
    submit = SubmitField('mark')
