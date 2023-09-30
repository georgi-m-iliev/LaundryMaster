import os

from flask import Blueprint, render_template, request, redirect, flash
from flask_security import SQLAlchemyUserDatastore, Security, login_user, verify_password, logout_user, hash_password, current_user
from flask_mail import Mail, Message
from itsdangerous import TimedSerializer

from app.db import db
from app.models import User, Role, LoginForm, EditProfileForm, RequestPasswordResetForm, PasswordResetForm

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
            if login_user(User.query.filter_by(username=form.username.data).first(), authn_via=['password']):
                # login is successful redirect to next argument from url
                user.last_login = db.func.current_timestamp()
                db.session.commit()
                return redirect(request.args.get('next') or '/')
            else:
                flash("Login failed")
        else:
            if user:
                flash('Wrong password')
            else:
                flash('User does not exist')

    return render_template('login.html', form=form)


@auth.route('/logout')
def logout():
    logout_user()
    return redirect('/login')


@auth.route('/password_reset', methods=['GET', 'POST'])
def password_reset():
    serializer = TimedSerializer(os.getenv('FLASK_SECRET_KEY'))

    if request.args.get('token') is None:
        form = RequestPasswordResetForm()

        if form.validate_on_submit():
            user = User.query.filter_by(email=form.email.data).first()
            if user is None:
                flash('Email is wrong or user does not exist.')
            else:
                token = serializer.dumps({'user_id': user.id, 'email': user.email}).encode('utf-8').hex()
                msg = Message()
                msg.subject = 'Password Reset Request - LaundryMaster'
                msg.recipients = [user.email]
                msg.sender = os.getenv('FLASK_MAIL_SENDER')
                msg.body = ('To reset your password, visit the following link:\n'
                            f'{request.url_root}password_reset?token={token}\n')
                mail.send(msg)
                flash('Email sent!')
            return redirect(request.base_url)
    else:
        form = PasswordResetForm()
        token = request.args.get('token')
        try:
            data = serializer.loads(bytes.fromhex(token), max_age=600)
        except itsdangerous.exc.SignatureExpired:
            flash('Token is invalid or expired.')
            return redirect(request.base_url)
        if form.validate_on_submit():
            print(data['user_id'])
            user = User.query.filter_by(id=data['user_id']).first()
            if user is None:
                flash('Password change failed! User does not exist.')
            else:
                user.password = hash_password(form.password.data)
                login_user(user, authn_via=['email'])
                db.session.commit()
                return redirect('/')
    return render_template('password_reset.html', form=form)
