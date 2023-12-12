import logging

from flask import Flask, send_from_directory, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

from app.db import db, migrate
from app.models import User, Role
from app.tasks import celery_init_app

from app.auth import auth, user_datastore, security, mail
from app.views import views
from app.api import api
from app.admin import admin


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_prefixed_env()

    if not app.debug:
        logging.basicConfig(
            filename='latest.log',
            format='%(asctime)s %(levelname)-8s %(message)s',
            level=logging.INFO,
            datefmt='%Y-%m-%d %H:%M:%S'
        )

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
    app.register_blueprint(admin, url_prefix='/admin')

    @app.route('/manifest.json')
    def manifest():
        return send_from_directory('static', 'manifest.json')

    @app.route('/sw.js')
    def service_worker():
        response = make_response(send_from_directory('static', 'sw.js'))
        response.headers['Content-Type'] = 'application/javascript'
        response.headers['Cache-Control'] = 'no-cache'
        return response

    db.init_app(app)
    migrate.init_app(app, db)

    security.init_app(app, user_datastore)
    mail.init_app(app)

    app.config.from_mapping(
        CELERY=dict(
            broker_url="redis://localhost",
            result_backend="redis://localhost",
            task_ignore_result=True,
        ),
    )
    celery_init_app(app)

    return app
