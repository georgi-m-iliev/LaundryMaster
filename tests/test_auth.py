import pytest


def test_login(client, app):
    assert client.get('/login').status_code == 200
    response = client.post(
        '/login', data={'username': 'ivan', 'password': 'password', 'login': ''}
    )

    # there should be no alerts for successful login
    assert str(response.data).find('alert') == -1
    # check that the user is logged in and redirected to the index page
    assert response.headers['Location'] == '/'


def test_logout(client, app):
    # login using the test_login function
    test_login(client, app)
    # make sure the user is logged in
    index_request = client.get('/')
    assert index_request.status_code == 200
    assert len(index_request.history) == 0

    # logout
    logout_request = client.get('/logout')
    assert logout_request.status_code == 302
    assert logout_request.headers['Location'] == '/login'
