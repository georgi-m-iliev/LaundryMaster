from flask import Blueprint, request, render_template
from flask_security import login_required
from flask_security.utils import hash_password

from app.db import db
from app.auth import user_datastore

admin = Blueprint('admin', __name__)


@admin.route('/', methods=['GET'])
def test():
    return render_template('admin/index.html')
