import os
import pytest
import tempfile
from dotenv import load_dotenv
from sqlalchemy.sql import text

from app import create_app
from app.db import db

with open(os.path.join(os.path.dirname(__file__), 'data.sql'), 'rb') as f:
    _data_sql = f.read().decode('utf8')

load_dotenv()


@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp()

    class TestConfig:
        TESTING = True
        SECRET_KEY = 'test91b801204a43803a3391979a'
        SECURITY_PASSWORD_SALT = 'dfWxHGdVuLwU'
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path}'
        WTF_CSRF_ENABLED = False

    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
        with db.engine.begin() as conn:
            for statement in _data_sql.split(';'):
                conn.execute(text(statement))

    # print(db_path)

    yield app

    os.close(db_fd)
    # os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()
