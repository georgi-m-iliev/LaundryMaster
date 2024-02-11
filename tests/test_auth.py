import pytest


def login(client, app, username, password):
    """ Login helper function """
    return client.post(
        '/login', data={'username': username, 'password': password, 'login': ''}
    )


def test_login(client, app):
    """ Testing login works with correct credentials """
    assert client.get('/login').status_code == 200
    response = login(client, app, 'ivan', 'password')

    # there should be no alerts for successful login
    assert str(response.data).find('alert') == -1
    # check that the user is logged in and redirected to the index page
    assert response.headers['Location'] == '/'


def test_login_failed(client, app):
    """ Testing login fails with incorrect credentials """
    assert client.get('/login').status_code == 200
    response = login(client, app, 'ivan', 'wrong_password')

    # check that the user is not redirected to the login page, login wasn't successful
    assert 'Location' not in response.headers


def test_logout(client, app):
    """ Testing logout """
    # login using the login helper function
    login(client, app, 'ivan', 'password')
    # make sure the user is logged in
    index_request = client.get('/')
    assert index_request.status_code == 200
    assert len(index_request.history) == 0

    # logout
    logout_request = client.get('/logout')
    assert logout_request.status_code == 302
    assert logout_request.headers['Location'] == '/login'
