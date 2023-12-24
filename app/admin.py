from flask import Blueprint, request, render_template
from flask_security import roles_required

from app.db import db
from app.auth import user_datastore

admin = Blueprint('admin', __name__)


@admin.route('/', methods=['GET'])
@roles_required('admin')
def test():
    return render_template('admin/index.html')
