import os
import pytest
from unittest.mock import Mock, patch, call

from flask_security.utils import verify_password

import app.api
from app.api import *
from app.models import User

from tests.test_auth import login

os.environ['FLASK_API_SECRET_KEY'] = 'test_key'


def test_add_user(client, app):
    """ Testing adding a user through the API. """
    response = client.post(
        '/api/add_user',
        data={'first_name': 'name', 'email': 'test@email.com', 'username': 'test_user', 'password': 'test_password'},
        headers={'Authorization': f'Bearer {os.getenv("FLASK_API_SECRET_KEY")}'}
    )
    assert response.status_code == 200
    assert response.json == {'status': 'success'}
    with app.test_request_context():
        assert User.query.filter_by(username='test_user').first()


def test_reset_password(client, app):
    """ Testing resetting a user's password through the API. """
    with app.test_request_context():
        user = User.query.filter_by(username='ivan').first()
        old_password = user.password
        response = client.post(
            '/api/reset_password',
            data={'username': user.username, 'password': 'new_password'},
            headers={'Authorization': f'Bearer {os.getenv("FLASK_API_SECRET_KEY")}'}
        )

        db.session.refresh(user)

        assert response.status_code == 200
        assert response.json == {'status': 'success'}
        assert user.password != old_password
        assert verify_password('new_password', user.password)


@patch('app.api.send_push_to_all')
def test_trigger_push(mock_send_push_to_all, client, app):
    """ Testing triggering a push notification. """
    login(client, app, 'georgi', 'password')

    notification = NotificationURL(title='test', body='test', icon='test', url='test')
    response = client.post(
        '/api/trigger_push',
        json={
            'title': notification.title,
            'body': notification.body,
            'icon': notification.icon,
            'url': notification.url
        },
    )

    assert response.status_code == 200
    assert response.json == {'status': 'success'}
    assert mock_send_push_to_all.called
    assert mock_send_push_to_all.call_args[1]['notification'].title == notification.title
    assert mock_send_push_to_all.call_args[1]['notification'].body == notification.body
    assert mock_send_push_to_all.call_args[1]['notification'].icon == notification.icon
    assert mock_send_push_to_all.call_args[1]['notification'].url == notification.url


@patch('app.api.send_push_to_all')
def test_trigger_push_unauthorized(mock_send_push_to_all, client, app):
    """ Testing triggering a push notification with a non-privileged user. """
    login(client, app, 'ivan', 'password')

    notification = NotificationURL(title='test', body='test', icon='test', url='test')
    response = client.post(
        '/api/trigger_push',
        json={
            'title': notification.title,
            'body': notification.body,
            'icon': notification.icon,
            'url': notification.url
        },
    )

    assert response.status_code == 403
    assert not mock_send_push_to_all.called


@patch('app.api.send_push_to_user')
def test_trigger_push_by_id(mock_send_push_to_all, client, app):
    """ Testing triggering a push notification to a user by id. """
    with app.test_request_context():
        login(client, app, 'georgi', 'password')
        receiver_user = User.query.filter_by(username='andrei').first()

        notification = NotificationURL(title='test', body='test', icon='test', url='test')
        response = client.post(
            f'/api/trigger_push/{receiver_user.id}',
            json={
                'title': notification.title,
                'body': notification.body,
                'icon': notification.icon,
                'url': notification.url
            },
        )

        assert response.status_code == 200
        assert response.json == {'status': 'success'}
        assert mock_send_push_to_all.called
        assert mock_send_push_to_all.call_args[1]['user'] == receiver_user
        assert mock_send_push_to_all.call_args[1]['notification'].title == notification.title
        assert mock_send_push_to_all.call_args[1]['notification'].body == notification.body
        assert mock_send_push_to_all.call_args[1]['notification'].icon == notification.icon
        assert mock_send_push_to_all.call_args[1]['notification'].url == notification.url


@patch('app.api.send_push_to_all')
def test_trigger_push_by_id_unauthorized(mock_send_push_to_all, client, app):
    """ Testing triggering a push notification to a user by id with a non-privileged user. """
    with app.test_request_context():
        login(client, app, 'ivan', 'password')
        receiver_user = User.query.filter_by(username='andrei').first()

        notification = NotificationURL(title='test', body='test', icon='test', url='test')
        response = client.post(
            f'/api/trigger_push/{receiver_user.id}',
            json={
                'title': notification.title,
                'body': notification.body,
                'icon': notification.icon,
                'url': notification.url
            },
        )

        assert response.status_code == 403
        assert not mock_send_push_to_all.called
