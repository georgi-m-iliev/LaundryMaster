from app import db

from flask_security import UserMixin, RoleMixin
from sqlalchemy import func

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
    splits = db.relationship('WashingCycleSplit', backref='washing_cycle', lazy=True)


class WashingCycleSplit(db.Model):
    __tablename__ = 'split_cycles'
    cycle_id = db.Column(db.Integer, db.ForeignKey('washing_cycles.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    paid = db.Column(db.Boolean(), default=False)
    accepted = db.Column(db.Boolean(), default=False)


class WashingMachine(db.Model):
    __tablename__ = 'washing_machine'
    id = db.Column(db.Integer, primary_key=True)
    currentkwh = db.Column(db.Numeric(20, 4))
    costperkwh = db.Column(db.Numeric(10, 2))
    public_wash_cost = db.Column(db.Numeric(10, 2))
    notification_task_id = db.Column(db.String(512))
    candy_device_id = db.Column(db.String(512), nullable=False)
    candy_appliance_id = db.Column(db.String(512), nullable=False)
    candy_api_token = db.Column(db.String(5000), nullable=True)
    candy_api_refresh_token = db.Column(db.String(512), nullable=True)
    candy_appliance_data = db.Column(db.PickleType, nullable=True)


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
    notification_task_id = db.Column(db.String(512), nullable=True)


class Notification:
    def __init__(self, title, body, icon):
        self.title = title
        self.body = body
        self.icon = icon
        self.url = '/'

    def __dict__(self):
        return {
            'title': self.title,
            'body': self.body,
            'icon': self.icon,
            'url': self.url
        }


class NotificationURL(Notification):
    def __init__(self, title, body, icon, url):
        super().__init__(title, body, icon)
        self.url = url


class NotificationActions(NotificationURL):
    def __init__(self, title, body, icon, url=None, actions=None):
        if url is None:
            url = '/'
        super().__init__(title, body, icon, url)
        if actions is None:
            self.actions = []
        else:
            self.actions = actions

    def add_action(self, action, title, url, icon=None):
        self.actions.append({'action': action, 'title': title, 'url': url})
        if icon is not None:
            self.actions[-1]['icon'] = icon

    def __dict__(self):
        result = super().__dict__()
        # each actions is a dict with keys 'action', 'title', 'url'
        result['actions'] = [{'action': action['action'], 'title': action['title']} for action in self.actions]
        result['actionsURLs'] = [action['url'] for action in self.actions]
        return result


schedule_reminder_notification = Notification(
    title="You have a scheduled washing!",
    body="Click here to see the details.",
    icon="cycle-reminder-icon.png"
)

cycle_paused_notification = Notification(
    title="Your cycle is paused!",
    body="Probably a glitch, go fix it!",
    icon="cycle-reminder-icon.png"
)

cycle_ended_notification = Notification(
    title="Your cycle has ended!",
    body="Go pick your laundry!",
    icon="cycle-done-icon.png"
)

cycle_termination_reminder_notification = Notification(
    title="Your cycle is still running...",
    body="Did you forget to terminate it?",
    icon="cycle-reminder-icon.png",
)

unpaid_cycles_reminder_notification = Notification(
    title='You have unpaid cycles!',
    body='Please pay your debt to the washing machine owner!',
    icon='unpaid-cycles-remind-icon.png'
)


class SplitRequestNotification(NotificationActions):
    def __init__(self, initiator: User, cycle: WashingCycle):
        super().__init__(
            title=f"You have a new split request!",
            body=f"{initiator.first_name} wants to split a washing cycle with you.\n"
                 f"Data: {cycle.end_timestamp.strftime('%d/%m/%Y %H:%M')}\n"
                 f"Amount: {cycle.cost} lv.",
            icon="split-icon.png",
            url=f'/usage/split/{cycle.id}',
            actions=[
                {'action': 'accept', 'title': 'Accept', 'url': f'/usage/split/{cycle.id}/accept'},
                {'action': 'reject', 'title': 'Reject', 'url': f'/usage/split/{cycle.id}/reject'}
            ]
        )
