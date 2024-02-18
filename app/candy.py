import os
import json
import requests
import datetime
from enum import Enum
from typing import Optional

from flask_wtf import FlaskForm
from sqlalchemy.exc import OperationalError

from flask import current_app
from wtforms import SelectField, BooleanField, SubmitField, ValidationError

from app.db import db
from app.models import WashingMachine, User


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


class ProgramType(Enum):
    WASH = 'wash'
    DRY = 'dry'
    COMB = 'comb'


class ProgramWashTemperature(Enum):
    ZERO = 0
    TWENTY = 20
    THIRTY = 30
    FORTY = 40
    SIXTY = 60
    NINETY = 90


class ProgramWashSpinSpeed(Enum):
    ZERO = (0, 0)
    FORTY = (4, 400)
    EIGHTY = (8, 800)
    THOUSAND = (10, 1000)
    FOURTEEN_HUNDRED = (14, 1400)


class ProgramWashSoilLevel(Enum):
    ZERO = 0


class ProgramDryLevel(Enum):
    NO_DRY = (0, 'No dry')
    IRON_DRY = (2, 'Iron dry')
    CUPBOARD_DRY = (3, 'Cupboard dry')
    EXTRA_DRY = (1, 'Extra dry')


class StartProgramForm(FlaskForm):
    from app.candy import ProgramWashTemperature, ProgramWashSpinSpeed, ProgramWashSoilLevel, ProgramDryLevel

    type = SelectField('type', choices=[('', ''), ('wash', 'Wash'), ('dry', 'Dry'), ('comb', 'Wash & Dry')])

    wash_program = SelectField('wash_program')
    wash_temp = SelectField('wash_temp', choices=[e.value for e in ProgramWashTemperature], default=40)
    wash_spin_speed = SelectField('wash_spin_speed', choices=[e.value for e in ProgramWashSpinSpeed], default=10)
    wash_soil_level = SelectField('wash_soil_level', choices=[e.value for e in ProgramWashSoilLevel])
    dry_after = BooleanField('dry_after')

    dry_program = SelectField('dry_program')
    dry_level = SelectField('dry_level',
                            choices=[e.value for e in ProgramDryLevel if e.name != 'NO_DRY'],
                            default=2)

    comb_program = SelectField('comb_program')
    comb_temp = SelectField('comb_temp', choices=[e.value for e in ProgramWashTemperature], default=40)
    comb_spin_speed = SelectField('comb_spin_speed', choices=[e.value for e in ProgramWashSpinSpeed], default=10)
    comb_soil_level = SelectField('comb_soil_level', choices=[e.value for e in ProgramWashSoilLevel])
    comb_dry_level = SelectField('comb_dry_level',
                                 choices=[e.value for e in ProgramDryLevel if e.name != 'NO_DRY'],
                                 default=2)

    start_program_submit = SubmitField('Start', id='start-program-submit', name='start-program-submit')
    stop_program_submit = SubmitField('Stop', id='stop-program-submit', name='stop-program-submit')
    pause_program_submit = SubmitField('Pause', id='pause-program-submit', name='pause-program-submit')

    def __init__(self):
        from app.candy import CandyWashingMachine
        super().__init__()
        CandyWashingMachine.get_programs()
        self.wash_program.choices = [(p['id'], p['name']) for p in CandyWashingMachine.programs if p['program_type'] == 'W']
        self.dry_program.choices = [(p['id'], p['name']) for p in CandyWashingMachine.programs if p['program_type'] == 'D']
        self.comb_program.choices = [(p['id'], p['name']) for p in CandyWashingMachine.programs if p['program_type'] == 'W' and p['drying_type']]

    def validate_type(form, field):
        if field.data == 'wash':
            if form.wash_program.data == '':
                raise ValidationError('Please select a wash program')
        elif field.data == 'dry':
            if form.dry_program.data == '':
                raise ValidationError('Please select a dry program')
        elif field.data == 'comb':
            if form.comb_program.data == '':
                raise ValidationError('Please select a comb program')
        else:
            raise ValidationError('Please select a program type')


class CandyWashingMachine:
    _instance = None
    _instance_initialized = None
    last_updated = None
    programs = []
    downloaded_programs = []

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            print('Singleton class has no instance yet, creating one...')
            cls._instance = super(CandyWashingMachine, cls).__new__(cls)
            cls._instance_initialized = False
        else:
            print('Singleton class already has an instance, returning it...')
        return cls._instance

    def __init__(self):

        if self._instance_initialized:
            print('Singleton class already initialized, updating it...')
            self.update()
            return
        print('Initializing singleton class...')
        self._instance_initialized = True
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
        self.update()

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

    # @classmethod
    # def get_instance(cls):
    #     obj = cls()
    #     obj.update()
    #     return obj

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
            'fill_percent': self.fill_percent,
            'last_updated': self.last_updated.strftime('%Y-%m-%d %H:%M:%S') if self.last_updated else None
        }

    def json(self):
        return json.dumps(self.asdict())

    def update_db_model(self):
        washing_machine = WashingMachine.query.first()
        washing_machine.candy_appliance_data = self.asdict()
        db.session.commit()

    def update(self):
        if self.last_updated and (datetime.datetime.now() - self.last_updated).seconds < int(os.getenv('CANDY_VALIDITY', 60)):
            print('CWM is up to date!')
            return
        print('Updating CWM...')
        self.last_updated = datetime.datetime.now()
        data = fetch_appliance_data()
        self.current_status = data['appliance']['current_status']
        self.parse_current_status_parameters(data['appliance']['current_status_parameters'])
        if self.program_state == CandyWashProgramState.STOPPED:
            self.remaining_minutes = 0
        try:
            self.update_db_model()
        except OperationalError as e:
            current_app.logger.error(f'While updating CWM object: Failed to update DB model. Error: {e}')
            return False

    @classmethod
    def get_programs(cls):
        if not cls.programs:
            with open('resources/standard_programs.json', 'r') as f:
                cls.programs = json.load(f)
        if not cls.downloaded_programs:
            with open('resources/downloaded_programs.json', 'r') as f:
                cls.downloaded_programs = json.load(f)
        return cls.programs + cls.downloaded_programs

    @staticmethod
    def stop_program(user: User):
        current_app.logger.info(f'User {user.username} stopped the washing machine')
        body_args = {
            'Write': '1',
            'StSt': '0',
        }
        body = '&'.join(f'{key}={value}' for key, value in body_args.items())
        send_command(body)

    @staticmethod
    def trigger_pause_program(user: User):
        current_app.logger.info(f'User {user.username} triggered pause on the washing machine')
        body_args = {
            'Write': '1',
            'StSt': '3',
        }
        body = '&'.join(f'{key}={value}' for key, value in body_args.items())
        send_command(body)

    @staticmethod
    def start_program(user: User, start_program_form: StartProgramForm):
        body = process_start_program_form(start_program_form)
        current_app.logger.info(f'User {user.username} started program in mode: {start_program_form.type.data}')
        current_app.logger.debug(f'Sending command to start program: {body}')
        command_response = send_command(body)
        current_app.logger.debug(f'Response from Candy API: {command_response}')


def refresh_candy_token():
    """ Refreshes the Candy API token for the washing machine """
    washing_machine = WashingMachine.query.first()
    if not washing_machine.candy_api_refresh_token:
        current_app.logger.error('Tried to refresh the bearer token, but failed. No refresh token found')
        raise RuntimeError('No refresh token found for Candy API')
    url = f'{os.getenv("CANDY_AUTH_ENDPOINT")}/services/oauth2/token?device_id={washing_machine.candy_device_id}'

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
    washing_machine = WashingMachine.query.first()
    if not washing_machine.candy_api_token:
        refresh_candy_token()

    url = f'{os.getenv("CANDY_API_ENDPOINT")}/api/v1/appliances/{washing_machine.candy_appliance_id}.json?with_programs=0'

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
        refresh_candy_token()
        return fetch_appliance_data()
    elif response.status_code != 200:
        current_app.logger.error(f'Tried to fetch data from Candy API, but failed. More info: {response.text}')
        raise RuntimeError('Failed to fetch data from Candy API')

    return response.json()


def send_command(command_body: str):
    """ Sends command to washing machine through Candy API """
    washing_machine = WashingMachine.query.first()
    if not washing_machine.candy_api_token:
        refresh_candy_token()

    url = f'{os.getenv("CANDY_API_ENDPOINT")}/api/v1/commands.json'

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

    response = requests.request("POST", url, headers=headers, data=json.dumps({
        "appliance_id": washing_machine.candy_appliance_id,
        "body": command_body
    }))
    if response.status_code == 401:
        refresh_candy_token()
        return send_command(command_body)
    elif response.status_code != 200:
        current_app.logger.error(f'Tried to send command to washing machine, but failed. More info: {response.text}')
        raise RuntimeError('Failed to send command to washing machine')

    return response.json()


def process_start_program_form(start_program_form: StartProgramForm):
    """ Builds a command body for starting the washing machine through the Candy API. """
    body_args = {
        'Write': '1',
        'StSt': '1',
        'DelVl': '0',
        'PrNm': None,  # Program position from program_position
        'PrCode': None,  # from 'pr_code' field in programs
        'PrStr': None,  # Program name - human-readable
        'TmpTgt': '0',  # Washing temperature -  0, 20, 30, 40, to max
        'SLevTgt': '0',
        'SpdTgt': '0',  # Washing spin speed - divided by 100
        'OptMsk1': '0',
        'OptMsk2': '0',
        'Lang': '1',
        'Stm': '0',  # Steam - 0 or 'steam'
        'Dry': '3',  # From 'dry' field in programs
        'ED': '0',
        'RecipeId': '0',
        'StartCheckUp': '0',
        'DispTestOn': '1'
    }

    if start_program_form.type.data == 'wash':
        program_id = start_program_form.wash_program.data
        program = next(program for program in CandyWashingMachine.programs if program['id'] == program_id)
        body_args['PrNm'] = program['selector_position']
        body_args['PrCode'] = program['pr_code']
        body_args['PrStr'] = program['name']
        body_args['TmpTgt'] = start_program_form.wash_temp.data
        body_args['SpdTgt'] = start_program_form.wash_spin_speed.data
    elif start_program_form.type.data == 'dry':
        program_id = start_program_form.dry_program.data
        program = next(program for program in CandyWashingMachine.programs if program['id'] == program_id)
        body_args['PrNm'] = program['selector_position']
        body_args['PrCode'] = program['pr_code']
        body_args['PrStr'] = program['name']
        if program['dry'] == '255':
            body_args['Dry'] = start_program_form.dry_level.data
        else:
            body_args['Dry'] = program['dry']
    elif start_program_form.type.data == 'comb':
        program_id = start_program_form.comb_program.data
        program = next(program for program in CandyWashingMachine.programs if program['id'] == program_id)
        body_args['PrNm'] = program['selector_position']
        body_args['PrCode'] = program['pr_code']
        body_args['PrStr'] = program['name']
        body_args['TmpTgt'] = start_program_form.comb_temp.data
        body_args['SpdTgt'] = start_program_form.comb_spin_speed.data
        body_args['Dry'] = start_program_form.comb_dry_level.data

    return '&'.join(f'{key}={value}' for key, value in body_args.items())
