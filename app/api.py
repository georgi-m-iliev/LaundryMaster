from flask import Blueprint

api = Blueprint('api', __name__)


@api.route('/')
def index():
    return '<h1>API</h1>'


@api.route('/update')
def update():
    return {'status': 'success'}
