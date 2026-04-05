import json
import logging
import time
from pydantic.dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict

from dataclasses import asdict

import requests

from smart_charger.lib.ctek.config_util import ConfigUtil

import urllib.parse

from smart_charger.lib.ctek.constants import DAYS, CURRENT_LIMITS
from smart_charger.lib.ctek.exceptions import InvalidTokenException

# --- Subclasses for nested structures ---


@dataclass
class TimePeriod:
    day: str
    hour: int
    minute: int


@dataclass
class Period:
    start: TimePeriod
    stop: TimePeriod
    limit: float


@dataclass
class ChargingSchedule:
    id: Optional[int]
    device_id: str
    unit: str
    period_list: List[Period]
    connector_id: int
    active: bool
    user_enabled: bool
    time_zone: str
    pending_deletion: bool = False
    author_id: Optional[int] = None


@dataclass
class ChargingSchedules:
    list: List[ChargingSchedule]
    total_pages: int
    total_elements: int
    current_page: int
    page_size: int


@dataclass
class ChargingSessionSummary:
    device_id: str
    ongoing_transaction: bool
    transaction_id: int
    watt_hours_consumed: int
    momentary_voltage: Optional[str]
    momentary_power: Optional[str]
    momentary_current: Optional[str]
    device_online: bool
    type: str
    start_time: Optional[datetime]
    last_updated_time: Optional[datetime]


@dataclass
class Connector:
    id: int
    deviceId: str
    currentStatus: str
    statusReason: str
    statusString: str
    status: int
    startDate: Optional[datetime]
    updateDate: Optional[datetime]


@dataclass
class ConnectorSchedule:
    enabled: bool
    active: bool
    overridden: bool


@dataclass
class Schedule:
    device_id: str
    connectors: Dict[str, ConnectorSchedule]


@dataclass
class Configuration:
    auth_mode_active: bool


@dataclass
class ThirdPartyOcppInfo:
    provider_id: Optional[str]
    raw_url: Optional[str]
    enabled: bool
    username: Optional[str]
    password: Optional[str]


# --- Main class ---


@dataclass
class DeviceInfo:
    device_name: Optional[str]
    connectors: List[Connector]
    hardware_id: str
    device_type: str
    connected: bool
    model: str
    schedule: Schedule
    configuration: Configuration
    deviceId: str
    firmwareId: str
    firmwareVersion: str
    loadBalancingOnboarded: bool
    thirdPartyOcppInfo: ThirdPartyOcppInfo
    modelId: str


class LoginUtil:
    def __init__(self, config_util: ConfigUtil):
        self.config_util = config_util
        self.config = config_util.get_config()
        self.credentials_cache = config_util.get_credentials_cache()
        self.client_id = self.config.charger.ctek.client_id
        self.client_secret = self.config.charger.ctek.client_secret
        self.password = self.config.charger.ctek.password
        self.username = self.config.charger.ctek.username
        self.logger = logging.getLogger(__name__)

    def login(self) -> str:
        # Valid access token
        if (
            self.credentials_cache.access_token
            and time.time() < self.credentials_cache.token_expires
        ):
            expires = int(self.credentials_cache.token_expires - time.time())
            self.logger.info(f"Valid access token found. Expires in {expires} seconds")

        # Try with refresh token
        elif self.credentials_cache.refresh_token:
            self.logger.info(
                f"Login with refresh token {self.credentials_cache.refresh_token}"
            )
            try:
                response = self.login_with_refresh_token(
                    refresh_token=self.credentials_cache.refresh_token
                )
            except InvalidTokenException:
                # No valid token, login again
                self.logger.info("Token expired, logging in again")
                response = self.get_token()
                self.process_login_response(response)
            if response.get("access_token"):
                self.process_login_response(response)
            elif response.get("error") == "invalid_grant":
                self.logger.info("Invalid refresh token")
                response = self.get_token()
                self.process_login_response(response)
            else:
                self.logger.info("Error logging in")
                self.logger.info(response)
                raise InvalidTokenException("Failed to login")

        # No valid token
        else:
            self.logger.info("Token expired, login again")
            response = self.get_token()
            self.process_login_response(response)

        # Set access token
        return self.credentials_cache.access_token

    def process_login_response(self, response):
        self.logger.info(response)
        ts = int(time.time() + response["expires_in"])

        self.credentials_cache.access_token = response["access_token"]
        self.credentials_cache.refresh_token = response.get("refresh_token")
        self.credentials_cache.token_expires = ts

        self.config_util.save_credentials_cache(self.credentials_cache)

    def login_with_refresh_token(self, refresh_token):
        url = "https://iot.ctek.com/oauth/token"
        payload = f"client_id={self.client_id}&client_secret={self.client_secret}&grant_type=refresh_token&refresh_token={refresh_token}"
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": "CTEK/2.4.0 (se.ctek.ctekapp; build:3; iOS 15.5.0) Alamofire/2.4.0",
            "accept-language": "sv-SE;q=1.0, en-SE;q=0.9",
        }
        response = requests.request("POST", url, data=payload, headers=headers)
        self.logger.info(response.text)
        if response.status_code != 200:
            raise InvalidTokenException("Failed to get token from refresh token")

        return json.loads(response.text)

    def get_token(self):
        url = "https://iot.ctek.com/oauth/token"
        query_string = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "password",
            "password": self.password,
            "username": self.username,
        }
        payload = urllib.parse.urlencode(query_string)
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": "CTEK/2.4.0 (se.ctek.ctekapp; build:3; iOS 15.5.0) Alamofire/2.4.0",
            "accept-language": "sv-SE;q=1.0, en-SE;q=0.9",
        }

        response = requests.request("POST", url, data=payload, headers=headers)
        self.logger.info("LogiN: ", response.text)
        if response.status_code != 200:
            raise InvalidTokenException("Failed to get token")

        res = json.loads(response.text)
        return res


class CTEK:
    def __init__(self, config_util: ConfigUtil):
        self.device_id = config_util.get_config().charger.device_id
        self.login_util = LoginUtil(config_util)
        self.access_token = self.login_util.login()
        self.logger = logging.getLogger(__name__)

    def login_if_needed(self):
        self.access_token = self.login_util.login()

    def get_schedules(self) -> ChargingSchedules:
        url = "https://iot.ctek.com/schedule/transactions"
        querystring = {"deviceId": self.device_id}
        headers = self._get_headers()
        response = requests.request("GET", url, headers=headers, params=querystring)
        if response.status_code != 200:
            raise Exception(f"Failed to get schedules: {response.text}")

        charging_dict = json.loads(response.text)
        return ChargingSchedules(**charging_dict["charging_schedules"])

    def delete_schedule(self, id):
        url = "https://iot.ctek.com/schedule/transaction"
        querystring = {"id": id}
        response = requests.request(
            "DELETE", url, headers=self._get_headers(), params=querystring
        )
        if response.status_code != 200:
            raise Exception(
                f"Failed to delete schedules: {response.status_code}, message: {response.text}"
            )

    def delete_all_schedules(self):
        url = "https://iot.ctek.com/schedule/transactions"
        querystring = {"deviceId": self.device_id}
        response = requests.request(
            "DELETE", url, headers=self._get_headers(), params=querystring, timeout=3
        )
        if response.status_code != 200:
            raise Exception(
                f"Failed to delete schedules: {response.status_code}, message: {response.text}"
            )

    def delete_all_schedules_old(self):
        schedules = self.get_schedules()
        for schedule in schedules.list:
            self.delete_schedule(schedule.id)

    def _get_headers(self):
        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "user-agent": "CTEK/2.4.0 (se.ctek.ctekapp; build:3; iOS 15.5.0) Alamofire/2.4.0",
            "accept-language": "sv-SE;q=1.0, en-SE;q=0.9",
            "authorization": f"Bearer {self.access_token}",
        }
        return headers

    def get_current_session(self) -> ChargingSessionSummary:
        url = f"https://iot.ctek.com/devices/{self.device_id}/sessions/current"
        headers = self._get_headers()
        response = requests.request("GET", url, headers=headers)
        if response.status_code != 200:
            self.ctek_error_handler(response)
        return ChargingSessionSummary(**json.loads(response.text))

    def get_status(self) -> DeviceInfo:
        url = f"https://iot.ctek.com/devices/{self.device_id}/status"

        headers = self._get_headers()

        response = requests.request("GET", url, headers=headers)
        if response.status_code != 200:
            self.ctek_error_handler(response)

        return DeviceInfo(**json.loads(response.text))

    def get_history(self, page_size=20, page=0, from_date=None, to_date=None):
        url = f"https://iot.ctek.com/api/v1/devices/{self.device_id}/sessions/charging"

        querystring = {
            "pageSize": f"{page_size}",
            "page": f"{page}",
            "fromDate": from_date,
            "toDate": to_date,
        }
        headers = self._get_headers()

        try:
            response = requests.request(
                "GET", url, headers=headers, params=querystring, timeout=15
            )
        except requests.exceptions.Timeout:
            return None
        if response.status_code != 200:
            self.ctek_error_handler(response)

        return json.loads(response.text)

    def set_schedules(self, schedules: list[Schedule], current_limit: int = 16):
        url = "https://iot.ctek.com/schedule/transaction"
        if current_limit not in CURRENT_LIMITS:
            raise Exception("Invalid current value")

        period_list = list(
            map(
                lambda schedule: {
                    "limit": current_limit,
                    "start": {
                        "day": schedule.start_day.name,
                        "hour": schedule.start_time.split(":")[0],
                        "minute": schedule.start_time.split(":")[1],
                    },
                    "stop": {
                        "day": schedule.stop_day.name,
                        "hour": schedule.stop_time.split(":")[0],
                        "minute": schedule.stop_time.split(":")[1],
                    },
                },
                schedules,
            )
        )

        payload = {
            "device_id": self.device_id,
            "period_list": period_list,
            "unit": "A",
            "time_zone": "+02:00",
        }

        self.logger.info(payload)

        response = requests.request(
            "POST", url, json=payload, headers=self._get_headers(), timeout=15
        )
        self.logger.info(f"set_schedules={response}")
        if response.status_code != 200:
            self.ctek_error_handler(response)

        return json.loads(response.text)

    def create_schedule(
        self,
        start_day: DAYS,
        start: str,
        stop_day: DAYS,
        stop: str,
        current_limit: int = 16,
    ):
        url = "https://iot.ctek.com/schedule/transaction"
        if current_limit not in CURRENT_LIMITS:
            raise Exception("Invalid current value")
        payload = {
            "device_id": self.device_id,
            "period_list": [
                {
                    "limit": current_limit,
                    "start": {
                        "day": start_day.name,
                        "hour": start.split(":")[0],
                        "minute": start.split(":")[1],
                    },
                    "stop": {
                        "day": stop_day.name,
                        "hour": stop.split(":")[0],
                        "minute": stop.split(":")[1],
                    },
                }
            ],
            "unit": "A",
            "time_zone": "+02:00",
        }

        response = requests.request(
            "POST", url, json=payload, headers=self._get_headers(), timeout=15
        )
        if response.status_code != 200:
            self.ctek_error_handler(response)

        return json.loads(response.text)

    def set_enable_charging(self, enable: bool):
        url = "https://iot.ctek.com/api/v3/device/control"
        headers = self._get_headers()

        payload = {
            "device_id": self.device_id,
            "instruction": "RESUME_CHARGING" if enable else "PAUSE_CHARGING",
            "connector_id": 1,
        }

        response = requests.request("POST", url, json=payload, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to pause charging: {response.text}")
        return json.loads(response.text)

    def create_schedule_v3(self, schedule: ChargingSchedule):
        url = "https://iot.ctek.com/api/v3/schedule/transaction"
        payload = asdict(schedule)
        headers = self._get_headers()

        response = requests.request(
            "POST", url, json=payload, headers=headers, params={"pushToDevice": True}
        )
        if response.status_code != 200:
            raise Exception(f"Failed to create schedule: {response.text}")

        schedule_data = json.loads(response.text)
        print(schedule_data)
        return ChargingSchedule(**schedule_data["data"])

    def get_schedule(self, schedule_id: int) -> ChargingSchedule:
        url = "https://iot.ctek.com/api/v3/schedule/transaction"
        querystring = {"id": schedule_id}
        headers = self._get_headers()
        response = requests.request("GET", url, headers=headers, params=querystring)
        if response.status_code != 200:
            raise Exception(f"Failed to get schedule: {response.text}")

        schedule_data = json.loads(response.text)
        print(schedule_data)
        return ChargingSchedule(**schedule_data)

    def update_schedule(self, schedule: ChargingSchedule):
        url = "https://iot.ctek.com/api/v3/schedule/transaction"

        payload = asdict(schedule)
        print(payload)

        querystring = {"pushToDevice": True}

        headers = self._get_headers()
        response = requests.request(
            "POST", url, json=payload, headers=headers, params=querystring
        )
        if response.status_code != 200:
            raise Exception(f"Failed to update schedule: {response.text}")

        return json.loads(response.text)

    # Sets the maximum current limit for the charger
    def set_max_current(self, current_limit: int):
        if current_limit not in CURRENT_LIMITS:
            raise Exception("Invalid current value")

        url = "https://iot.ctek.com/api/v3/device/configurations"
        payload = {"CurrentMaxAssignment": str(current_limit)}
        headers = self._get_headers()

        response = requests.request(
            "POST",
            url,
            json=payload,
            headers=headers,
            params={"deviceId": self.device_id, "pushToDevice": "true"},
        )
        if response.status_code != 200:
            raise Exception(f"Failed to set max current: {response.text}")

        return json.loads(response.text)

    def get_meter(self) -> int:
        latest = self.get_history(page_size=1)

        print(latest)

        meter_stop_ = latest["list"][0]["meter_stop"]
        return meter_stop_

    def ctek_error_handler(self, response):
        err = json.loads(response.text)
        if err["error"] == "invalid_token":
            raise InvalidTokenException()
        else:
            self.logger.info("Error handler: ", response.text)
            raise Exception(f"Failed to get history: {err}")
