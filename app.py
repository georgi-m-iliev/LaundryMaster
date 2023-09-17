from flask import Flask

from auth import auth
from views import views

app = Flask(__name__)


def main():
    app.config['SECRET_KEY'] = 'secret!'

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')

    app.run()


if __name__ == '__main__':
    main()
