from flask import Blueprint, render_template, request, redirect, flash
from flask_security import SQLAlchemyUserDatastore, login_user, verify_password, logout_user

from app.db import db

from app.models import User, Role, LoginForm, EditProfileForm, PasswordResetForm

auth = Blueprint('auth', __name__)

user_datastore = SQLAlchemyUserDatastore(db, User, Role)


@auth.route('/login', methods=['GET', 'POST'])
def login():
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
    reset_form = PasswordResetForm()
    return render_template('password_reset.html', form=reset_form)

