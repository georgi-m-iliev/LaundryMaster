import os
import requests
from dotenv import load_dotenv
import psycopg2

from app.functions import get_energy_consumption


def main():
    db = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME')
    )

    cursor = db.cursor()
    print("Successfully connected to database")

    try:
        consumption = get_energy_consumption()
        print("Current consumption is {} kwh.".format(consumption))
        cursor.execute('UPDATE public.washing_machine SET currentkwh = (%s) WHERE id = 1;', (consumption,))
        db.commit()
    except Exception as e:
        db.rollback()
        db.close()
        raise e
    finally:
        db.close()


if __name__ == '__main__':
    load_dotenv()
    main()
