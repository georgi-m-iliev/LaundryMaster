from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

from app.db import db, migrate
from app.models import User, Role

from app.auth import auth, user_datastore, security, mail
from app.views import views
from app.api import api


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_prefixed_env()

    test_config = None

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')
    app.register_blueprint(api, url_prefix='/api')

    db.init_app(app)
    migrate.init_app(app, db)

    security.init_app(app, user_datastore)
    mail.init_app(app)

    return app
