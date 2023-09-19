from flask import Blueprint, render_template, request, redirect

from app.models import LoginForm, EditProfileForm

auth = Blueprint('auth', __name__)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        return redirect('/')

    return render_template('login.html', form=form)


@auth.route('/logout')
def logout():
    pass