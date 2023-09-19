from flask import Blueprint, render_template, request, redirect
from flask_security import SQLAlchemyUserDatastore

from app.db import db

from app.models import User, Role, LoginForm, EditProfileForm

auth = Blueprint('auth', __name__)

user_datastore = SQLAlchemyUserDatastore(db, User, Role)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        return redirect('/')

    return render_template('login.html', form=form)


@auth.route('/logout')
def logout():
    pass