import os
import datetime

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectMultipleField, SelectField, FieldList
from wtforms import IntegerField, DateTimeLocalField, ValidationError, DateField, DecimalField
from wtforms.validators import DataRequired, Length, Email, EqualTo, Optional, NumberRange


class LoginForm(FlaskForm):
    username = StringField('username', validators=[DataRequired()])
    password = PasswordField('password',
                             validators=[DataRequired(), Length(min=6, max=128)],
                             render_kw={'type': 'password'}
                             )
    login = SubmitField('login', id='login', name='login')


class RequestPasswordResetForm(FlaskForm):
    email = StringField('email', validators=[DataRequired(), Email()])
    submit = SubmitField('Send email', id='email-submit', name='email-submit')


class PasswordResetForm(FlaskForm):
    password = PasswordField('password', validators=[Length(min=6, max=128)])
    password_confirm = PasswordField('password_again',
                                     validators=[
                                         Length(min=6, max=128),
                                         EqualTo('password', message="Passwords don't match"),
                                     ])
    submit = SubmitField('Save password', id='password-submit', name='password-submit')


class EditProfileForm(FlaskForm):
    first_name = StringField('first_name', validators=[Optional()], render_kw={'placeholder': 'First Name'})
    email = StringField('email', validators=[Email(), Optional()], render_kw={'placeholder': 'Email'})
    username = StringField('username', validators=[Optional()], render_kw={'placeholder': 'Username'})
    password = PasswordField(
        'password',
        validators=[Length(min=6, max=128), Optional()],
        render_kw={'placeholder': '********'}
    )
    password_confirm = PasswordField(
        'password_again',
        validators=[
            Length(min=6, max=128),
            EqualTo('password', message="Passwords don't match"),
            Optional()
        ],
        render_kw={'placeholder': '********'})
    profile_submit = SubmitField('Save Changes', id='profile-submit', name='profile-submit')


class EditSettingsForm(FlaskForm):
    automatic_stop = BooleanField(default=False)
    automatic_open_candy = BooleanField(default=True)
    settings_submit = SubmitField('Save Settings', id='settings-submit', name='settings-submit')


class EditRolesForm(FlaskForm):
    roles_to_add = SelectMultipleField('roles_to_add', choices=[])
    roles_to_remove = SelectMultipleField('roles_to_remove', choices=[])
    roles_submit = SubmitField('Save Roles', id='roles-submit', name='roles-submit')


class UsageViewShowCountForm(FlaskForm):
    items = SelectField('ShowCount', choices=[(10, '10'), (20, '20'), (50, '50'), (100, '100'), ('all', 'All')])


class UnpaidCyclesForm(FlaskForm):
    checkboxes = FieldList(BooleanField('checkboxes', default=False, validators=[Optional()]), min_entries=0)
    unpaid_submit = SubmitField('Mark Paid', id='unpaid-submit', name='unpaid-submit')


class ScheduleEventRequestForm(FlaskForm):
    id = IntegerField('id', validators=[Optional()])
    start_timestamp = DateTimeLocalField('start_timestamp', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    cycle_type = SelectField(
        'cycle_type',
        choices=[('both', 'Washing & Drying'), ('wash', 'Washing'), ('dry', 'Drying')]
    )
    event_submit = SubmitField('Schedule', id='event-submit', name='event-submit')

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
    other_users = SelectMultipleField('other_users', choices=[], coerce=int, validators=[DataRequired()])
    cycle_id = IntegerField('cycle_id', validators=[DataRequired()])
    split_submit = SubmitField('Split', id='split-submit', name='split-submit')


class MarkPaidForm(FlaskForm):
    cycle_id = IntegerField('cycle_id', validators=[DataRequired()])
    mark_paid_submit = SubmitField('Mark Paid', id='mark-paid-submit', name='mark-paid-submit')


class UpdateWashingMachineForm(FlaskForm):
    # costperkwh between 0.01 and 1.0
    costperkwh = DecimalField(
        'costperkwh',
        validators=[
            Optional(),
            NumberRange(min=0.01, max=1.0, message='kWh cost must be between 0.01 and 1.0')
        ]
    )
    public_wash_cost = DecimalField('public_wash_cost', validators=[Optional()])
    terminate_notification_task = SubmitField(id='terminate-notification-task', name='terminate-notification-task')
    update_washing_machine_submit = SubmitField('Update', id='update-wm-submit', name='update-wm-submit')


class StartProgramForm(FlaskForm):
    from app.candy import ProgramWashTemperature, ProgramWashSpinSpeed, ProgramWashSoilLevel, ProgramDryLevel

    type = SelectField('type', choices=[('', ''), ('wash', 'Wash'), ('dry', 'Dry'), ('comb', 'Wash & Dry')])

    wash_program = SelectField('wash_program')
    wash_temp = SelectField('wash_temp', choices=[e.value for e in ProgramWashTemperature], default=40)
    wash_spin_speed = SelectField('wash_spin_speed', choices=[e.value for e in ProgramWashSpinSpeed], default=10)
    wash_soil_level = SelectField('wash_soil_level', choices=[e.value for e in ProgramWashSoilLevel])
    dry_after = BooleanField('dry_after')

    dry_program = SelectField('dry_program')
    dry_level = SelectField('dry_level',
                            choices=[e.value for e in ProgramDryLevel if e.name != 'NO_DRY'],
                            default=2)

    comb_program = SelectField('comb_program')
    comb_temp = SelectField('comb_temp', choices=[e.value for e in ProgramWashTemperature], default=40)
    comb_spin_speed = SelectField('comb_spin_speed', choices=[e.value for e in ProgramWashSpinSpeed], default=10)
    comb_soil_level = SelectField('comb_soil_level', choices=[e.value for e in ProgramWashSoilLevel])
    comb_dry_level = SelectField('comb_dry_level',
                                 choices=[e.value for e in ProgramDryLevel if e.name != 'NO_DRY'],
                                 default=2)

    start_program_submit = SubmitField('Start', id='start-program-submit', name='start-program-submit')

    def __init__(self):
        from app.candy import CandyWashingMachine
        super().__init__()
        CandyWashingMachine.get_programs()
        self.wash_program.choices = [(p['id'], p['name']) for p in CandyWashingMachine.programs if p['program_type'] == 'W']
        self.dry_program.choices = [(p['id'], p['name']) for p in CandyWashingMachine.programs if p['program_type'] == 'D']
        self.comb_program.choices = [(p['id'], p['name']) for p in CandyWashingMachine.programs if p['program_type'] == 'W' and p['drying_type']]

    def validate_type(form, field):
        if field.data == 'wash':
            if form.wash_program.data == '':
                raise ValidationError('Please select a wash program')
        elif field.data == 'dry':
            if form.dry_program.data == '':
                raise ValidationError('Please select a dry program')
        elif field.data == 'comb':
            if form.comb_program.data == '':
                raise ValidationError('Please select a comb program')
        else:
            raise ValidationError('Please select a program type')
