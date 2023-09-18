from app import db
from flask_login import UserMixin
from sqlalchemy import func


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(128), unique=True)
    username = db.Column(db.String(128), unique=True)
    password = db.Column(db.String(512))
    first_name = db.Column(db.String(150))
    last_login = db.Column(db.DateTime(timezone=True))


class WashingCycles(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    startkwh = db.Column(db.Float)
    endkwh = db.Column(db.Float)
    start_timestamp = db.Column(db.DateTime(timezone=True), default=func.now())
    end_timestamp = db.Column(db.DateTime(timezone=True))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref=db.backref('washing_cycles', lazy=True))
