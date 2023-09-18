from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

from app.db import db

from app.auth import auth
from app.views import views


def init_db():
    db.create_all()


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    app.config['SECRET_KEY'] = 'secret!'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://laundrymaster:password@130.61.155.188:5432/laundrymaster'

    test_config = None

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')

    db.init_app(app)

    with app.app_context():
        db.create_all()

    return app
