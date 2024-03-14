from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_moment import Moment
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


db = SQLAlchemy()
migrate = Migrate()

moment = Moment()

limiter = Limiter(
    get_remote_address,
    default_limits=['200 per day', '50 per hour'],
)
