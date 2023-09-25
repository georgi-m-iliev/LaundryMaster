# LaundryMaster

## Description

This is a simple but useful web application made with the intention
to help my fellow students and me to manage your shared washing machine
which we will be using in our dormitory.

## Environment

This application is written in Python 3.11 and uses PostgreSQL as a database.
The full list of dependencies can be found in the `requirements.txt` file.

## Setting up the environment

1. Install and set up your Python environment and PostgreSQL DBMS.
2. Clone this repository.
3. Run `pip install -r requirements.txt` to install all the dependencies.
4. Migrate the database by running `flask db migrate` and then upgrade it by running `flask db upgrade`.
5. You are ready to go! Run `python main.py` to start the application.

## Usage

Open http://localhost:5000 in your favorite browser and enjoy!


## Deployment

There are many ways to deploy a Flask app. The simplest one is to install gunicorn via `pip install gunicorn`
and run the WSGI server with the following command `gunicorn --workers 4 --bind 0.0.0.0:5000 main:app`.
Adjust the number of workers and the port to your needs.


## License

This project is licensed under the GNU GPLv3 License - see the [LICENSE](LICENSE) file for details.