import os
import json
import requests
from enum import Enum
from typing import Optional

from flask import current_app

from app.db import db
from app.models import WashingMachine


class CandyStatusCode(Enum):
    def __init__(self, code: int, label: str):
        self.code = code
        self.label = label

    def __str__(self):
        return self.label

    def json(self):
        return json.dumps({'code': self.code, 'label': self.label})

    def asdict(self):
        return {'code': self.code, 'label': self.label}

    @classmethod
    def from_code(cls, code: int):
        for state in cls:
            if code == state.code:
                return state
        raise ValueError(f"Unrecognized code when parsing {cls}: {code}")


class CandyMachineState(CandyStatusCode):
    UNKNOWN = (-1, "Unknown")
    IDLE = (1, "Idle")
    RUNNING = (2, "Running")
    PAUSED = (3, "Paused")
    DELAYED_START_SELECTION = (4, "Delayed start selection")
    DELAYED_START_PROGRAMMED = (5, "Delayed start programmed")
    ERROR = (6, "Error")
    FINISHED1 = (7, "Finished")
    FINISHED2 = (8, "Finished")


class CandyWashProgramState(CandyStatusCode):
    UNKNOWN = (-1, "Unknown")
    STOPPED = (0, "Stopped")
    PRE_WASH = (1, "Pre-wash")
    WASH = (2, "Wash")
    RINSE = (3, "Rinse")
    LAST_RINSE = (4, "Last rinse")
    END = (5, "End")
    DRYING = (6, "Drying")
    ERROR = (7, "Error")
    STEAM = (8, "Steam")
    GOOD_NIGHT = (9, "Spin - Good Night")
    SPIN = (10, "Spin")


class CandyWashingMachine:
    def __init__(self):
        self.current_status = None
        self.machine_state: CandyMachineState = CandyMachineState.UNKNOWN
        self.program_state: CandyWashProgramState = CandyWashProgramState.UNKNOWN
        self.program: int = -1
        self.program_code: Optional[int] = None
        self.temp: int = -1
        self.spin_speed: int = -1
        self.remaining_minutes: int = -1
        self.remote_control: bool = False
        self.fill_percent: Optional[int] = None  # 0...100
        self.washing_machine: WashingMachine = WashingMachine.query.first()

    def parse_current_status_parameters(self, json_data):
        self.machine_state = CandyMachineState.from_code(int(json_data["MachMd"]))
        self.program_state = CandyWashProgramState.from_code(int(json_data["PrPh"]))
        self.program = int(json_data["Pr"]) if "Pr" in json_data else int(json_data["PrNm"])
        self.program_code = int(json_data["PrCode"]) if "PrCode" in json_data else None
        self.temp = int(json_data["Temp"])
        self.spin_speed = int(json_data["SpinSp"]) * 100
        self.remaining_minutes = round(int(json_data["RemTime"]) / 60)
        self.remote_control = json_data["WiFiStatus"] == "1"
        self.fill_percent = int(json_data["FillR"]) if "FillR" in json_data else None

    @classmethod
    def get_instance(cls):
        obj = cls()
        obj.update()
        return obj

    def asdict(self):
        return {
            'current_status': self.current_status,
            'machine_state': self.machine_state.asdict(),
            'program_state': self.program_state.asdict(),
            'program': self.program,
            'program_code': self.program_code,
            'temp': self.temp,
            'spin_speed': self.spin_speed,
            'remaining_minutes': self.remaining_minutes,
            'remote_control': self.remote_control,
            'fill_percent': self.fill_percent
        }

    def json(self):
        return json.dumps(self.asdict())

    def update_db_model(self):
        db.session.refresh(self.washing_machine)
        self.washing_machine.candy_appliance_data = self.asdict()
        db.session.commit()

    def update(self):
        data = fetch_appliance_data()
        self.current_status = data['appliance']['current_status']
        self.parse_current_status_parameters(data['appliance']['current_status_parameters'])
        self.update_db_model()


def refresh_candy_token(washing_machine: WashingMachine):
    url = 'https://account.candy-home.com/CandyApp/services/oauth2/token?device_id=b461fca47c039e37'

    payload = {'grant_type': 'hybrid_refresh',
               'client_id': os.getenv('CANDY_CLIENT_ID'),
               'refresh_token': washing_machine.candy_api_refresh_token,
               'format': 'json'}

    headers = {
        'User-Agent': 'SalesforceMobileSDK/10.2.0 android mobile/13 (M2012K11AG) simply-Fi/3.7.1(211) Native uid_b461fca47c039e37 ftr_AI.KT.UA SecurityPatch/2023-05-01',
        'Cookie': 'CookieConsentPolicy=0:1; LSKey-c$CookieConsentPolicy=0:1'
    }

    refresh_request = requests.post(url, headers=headers, data=payload)
    if refresh_request.status_code != 200:
        current_app.logger.error(f'Tried to refresh the bearer token, but failed. More info: {refresh_request.text}')
        raise RuntimeError('Failed to refresh Candy API token')
    washing_machine.candy_api_token = refresh_request.json()['id_token']
    db.session.commit()
    current_app.logger.info('Successfully refreshed Candy API token')


def fetch_appliance_data():
    """ Fetches appliance data from Candy API """
    washing_machine: WashingMachine = WashingMachine.query.first()
    if not washing_machine.candy_api_token:
        refresh_candy_token(washing_machine)

    url = f'https://simply-fi.herokuapp.com/api/v1/appliances/{washing_machine.candy_appliance_id}.json?with_programs=0'

    headers = {
        'Host': 'simply-fi.herokuapp.com',
        'Salesforce-Auth': '1',
        'Device-Language': 'en',
        'Device-Model': 'POCO M2012K11AG',
        'Device-Os': 'Android 13',
        'App-Version-Name': '3.7.1',
        'Player-Id': '3c08af96-fb58-4595-ba22-23afd515d03f',
        'App-Version-Code': '211',
        'Authorization': f'Bearer {washing_machine.candy_api_token}'
    }

    response = requests.request("GET", url, headers=headers)
    if response.status_code == 401:
        refresh_candy_token(washing_machine)
        return fetch_appliance_data()
    elif response.status_code != 200:
        current_app.logger.error(f'Tried to fetch data from Candy API, but failed. More info: {response.text}')
        raise RuntimeError('Failed to fetch data from Candy API')

    return response.json()
