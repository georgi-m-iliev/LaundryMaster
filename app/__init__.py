import logging
from sqlalchemy.exc import OperationalError
from werkzeug.middleware.proxy_fix import ProxyFix

from flask import Flask, send_from_directory, make_response, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

from app.db import db, migrate, moment, limiter
from app.models import User, Role
from app.tasks import celery_init_app

from app.auth import auth, user_datastore, security, mail
from app.views import views
from app.api import api, sock
from app.admin import admin


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    if test_config:
        app.config.from_object(test_config)
    else:
        app.config.from_prefixed_env()

    if not app.debug:
        logging.basicConfig(
            filename='latest.log',
            format='%(asctime)s %(levelname)-8s %(message)s',
            level=logging.INFO,
            datefmt='%Y-%m-%d %H:%M:%S'
        )

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

    if not app.debug:
        @app.errorhandler(OperationalError)
        def handle_db_error(e):
            app.logger.error(e)
            return render_template('error.html', code='5xx'), 500

        @app.errorhandler(404)
        def handle_404(e):
            return render_template('error.html', code='404'), 404

        @app.errorhandler(403)
        def handle_403(e):
            return render_template('error.html', code='403'), 403

        # @app.errorhandler(Exception)
        # def handle_exception(e):
        #     app.logger.error(e)
        #     return render_template('error.html', code=None), 500

    db.init_app(app)
    migrate.init_app(app, db)

    with app.app_context():
        # inits all tables in db
        db.create_all()

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

    sock.init_app(app)

    moment.init_app(app)

    if not app.debug:
        app.config['RATELIMIT_STORAGE_URI'] = 'redis://localhost:6379'
        app.config['RATELIMIT_STORAGE_OPTIONS'] = {'socket_connect_timeout': 30}
        app.config['RATELIMIT_KEY_PREFIX'] = 'fl_ratelimiter'
    else:
        app.config['RATELIMIT_ENABLED'] = False

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
    limiter.init_app(app)

    return app
