import os

from flask import Blueprint, render_template, request, redirect, flash
from flask_security import SQLAlchemyUserDatastore, Security, login_user, verify_password, logout_user, hash_password, current_user
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import itsdangerous.exc

from app.db import db
from app.models import User, Role
from app.forms import LoginForm, RequestPasswordResetForm, PasswordResetForm, EditProfileForm

auth = Blueprint('auth', __name__)

user_datastore = SQLAlchemyUserDatastore(db, User, Role)
security = Security()
mail = Mail()


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect('/')

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and verify_password(form.password.data, user.password):
            if login_user(User.query.filter_by(username=form.username.data).first(), authn_via=['password'], remember=True):
                # login is successful redirect to next argument from url
                user.last_login = db.func.current_timestamp()
                db.session.commit()
                return redirect(request.args.get('next') or '/')
            else:
                if not user.active:
                    flash('Your account is not active!', 'warning')
                else:
                    flash('Login failed', 'error')
        else:
            if user:
                flash('Wrong password', 'error')
            else:
                flash('User does not exist', 'warning')

    return render_template('auth/login.html', form=form)


@auth.route('/login/<token>', methods=['GET'])
def token_login(token):
    serializer = URLSafeTimedSerializer(os.getenv('FLASK_SECRET_KEY'))

    try:
        user_id = serializer.loads(token, salt='login-request', max_age=3600)
    except (BadSignature, SignatureExpired):
        return {'error': 'Invalid or expired token'}

    user = User.query.get(user_id)
    if not user:
        return {'error': 'Invalid user_id in token'}

    if login_user(user):
        return redirect('/')
    else:
        return {'error': 'Could not log you in'}


@auth.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out', 'success')
    return redirect('/login')


@auth.route('/password_reset', methods=['GET', 'POST'])
def password_reset():
    if current_user.is_authenticated:
        return redirect('/')

    serializer = URLSafeTimedSerializer(os.getenv('FLASK_SECRET_KEY'))

    # Check if token is supplied, is so, process the request and render the password reset form
    if request.args.get('token'):
        token = request.args.get('token')
        try:
            data = serializer.loads(bytes.fromhex(token), max_age=600)
        except itsdangerous.exc.BadTimeSignature:
            flash('Token is invalid or expired!\nPlease try again.', 'error')
            return redirect('/password_reset')
        except itsdangerous.exc.BadSignature:
            flash('Token is invalid!\nPlease try again.', 'error')
            return redirect('/password_reset')

        password_reset_form = PasswordResetForm()

        if password_reset_form.validate_on_submit():
            user = User.query.filter_by(id=data['user_id']).first()
            if user is None:
                flash('User does not exist.', 'warning')
                return redirect('/')
            else:
                user.password = hash_password(password_reset_form.password.data)
                db.session.commit()
                login_user(user, authn_via=['email'])
                return redirect('/')
        else:
            for field, errors in password_reset_form.errors.items():
                for error in errors:
                    flash(error)
        return render_template('auth/password_reset.html', form=password_reset_form)

    request_reset_form = RequestPasswordResetForm()

    if request_reset_form.validate_on_submit():
        user = User.query.filter_by(email=request_reset_form.email.data).first()
        if user is None:
            flash('Email is wrong or user does not exist.', 'warning')
        else:
            token = serializer.dumps({'user_id': user.id}).encode('utf-8').hex()
            email_data = {
                'title': 'Your password reset link has arrived!',
                'body': 'Hey, Georgi! If you still want to change your password, click the link below.',
                'link': f'{request.url_root}password_reset?token={token}'
            }
            msg = Message()
            msg.subject = 'Password Reset Request - LaundryMaster'
            msg.recipients = [user.email]
            msg.sender = os.getenv('FLASK_MAIL_SENDER')
            msg.body = render_template('auth/email.html', data=email_data)
            msg.html = render_template('auth/email.html', data=email_data)
            mail.send(msg)
            flash('Email sent!', 'success')
        return redirect(request.base_url)
    else:
        for field, errors in request_reset_form.errors.items():
            for error in errors:
                flash(error)

    return render_template('auth/password_reset.html', form=request_reset_form)
