from flask import Blueprint, render_template, request, redirect

auth = Blueprint('auth', __name__)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        print('POST')
        return redirect('/')

    return render_template('login.html')


@auth.route('/logout')
def logout():
    pass