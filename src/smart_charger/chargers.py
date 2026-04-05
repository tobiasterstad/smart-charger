from __future__ import annotations

import abc
import datetime
import enum
import json
import logging
import urllib.parse
from dataclasses import dataclass
from typing import Callable, Optional

import requests
from pydantic import BaseModel, PrivateAttr

from smart_charger.config import ChargerType
from smart_charger.lib.ctek.constants import CURRENT_LIMITS
from smart_charger.lib.ctek.exceptions import InvalidTokenException
from smart_charger.zaptec import ZaptecClient, ChargerCommands, OperatingMode

logger = logging.getLogger(__name__)


class ChargerStatus(enum.Enum):
    """
    Smart charger status categories, abstracted from specific charger operating modes.
    """

    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    CHARGING = "charging"
    PAUSED = "paused"
    FINISHED = "finished"


class ChargerReason(enum.Enum):
    NONE = "none"
    PAUSED_HIGH_LOAD = "high_load"
    CHARGING_SOLAR_ONLY = "solar_only"


class BaseCharger(abc.ABC, BaseModel):
    id: str
    status: ChargerStatus = ChargerStatus.DISCONNECTED
    reason: ChargerReason = ChargerReason.NONE
    current: float = 0
    read_only: bool = False

    @abc.abstractmethod
    def charger_type(self) -> ChargerType:
        raise NotImplementedError

    @abc.abstractmethod
    def start_charging(self) -> None:
        self.status = ChargerStatus.CHARGING

    @abc.abstractmethod
    def stop_charging(self) -> None:
        self.status = ChargerStatus.CONNECTED

    @abc.abstractmethod
    def set_current(self, current: float) -> None:
        if current != 0 and not (6 <= current <= 16):
            raise ValueError("Current must be 0 or between 6 and 16 A")
        self.current = current

    @abc.abstractmethod
    def get_status(self) -> OperatingMode:
        raise NotImplementedError

    @staticmethod
    def map_status(status: str) -> Optional[ChargerStatus]:
        raise NotImplementedError

    @staticmethod
    @abc.abstractmethod
    def get_connected_from_status(status: str) -> bool:
        raise NotImplementedError

    @staticmethod
    @abc.abstractmethod
    def get_charging_from_status(status: str) -> bool:
        raise NotImplementedError


class CtekOperatingMode(enum.Enum):
    """CTEK charger operating modes mapped from connector status strings."""

    Disconnected = "disconnected"
    Connected_Requesting = "connected_requesting"
    Connected_Charging = "connected_charging"
    Connected_Finished = "connected_finished"
    Error = "error"
    Unknown = "unknown"

    @staticmethod
    def from_connector_status(status_string: str) -> "CtekOperatingMode":
        normalized = status_string.lower().replace(" ", "_").replace("-", "_")
        status_map = {
            "disconnected": CtekOperatingMode.Disconnected,
            "available": CtekOperatingMode.Connected_Requesting,
            "preparing": CtekOperatingMode.Connected_Requesting,
            "charging": CtekOperatingMode.Connected_Charging,
            "suspended_ev": CtekOperatingMode.Connected_Requesting,
            "suspended_evse": CtekOperatingMode.Connected_Requesting,
            "finishing": CtekOperatingMode.Connected_Finished,
            "finished": CtekOperatingMode.Connected_Finished,
            "reserved": CtekOperatingMode.Connected_Requesting,
            "unavailable": CtekOperatingMode.Disconnected,
            "faulted": CtekOperatingMode.Error,
        }
        return status_map.get(normalized, CtekOperatingMode.Unknown)

    def to_operating_mode(self) -> OperatingMode:
        mapping = {
            CtekOperatingMode.Disconnected: OperatingMode.Disconnected,
            CtekOperatingMode.Connected_Requesting: OperatingMode.Connected_Requesting,
            CtekOperatingMode.Connected_Charging: OperatingMode.Connected_Charging,
            CtekOperatingMode.Connected_Finished: OperatingMode.Connected_Finished,
            CtekOperatingMode.Error: OperatingMode.Disconnected,
            CtekOperatingMode.Unknown: OperatingMode.Disconnected,
        }
        return mapping.get(self, OperatingMode.Disconnected)


@dataclass
class CtekConnectorInfo:
    """Information about a CTEK charger connector."""

    id: int
    device_id: str
    current_status: str
    status_reason: str
    status_string: str
    status: int


@dataclass
class CtekDeviceInfo:
    """CTEK device information returned by the status API."""

    device_id: str
    device_name: str
    connectors: list[CtekConnectorInfo]
    connected: bool


class CtekClient:
    """HTTP client for the CTEK IoT API with OAuth2 authentication and token persistence."""

    TOKEN_URL = "https://iot.ctek.com/oauth/token"
    BASE_URL = "https://iot.ctek.com"
    USER_AGENT = "CTEK/2.4.0 (se.ctek.ctekapp; build:3; iOS 15.5.0) Alamofire/2.4.0"
    REQUEST_TIMEOUT = 15

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
        device_id: str,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        token_expires_at: Optional[datetime.datetime] = None,
        on_token_refreshed: Optional[Callable[[str, int], None]] = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.password = password
        self.device_id = device_id
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_expires_at = token_expires_at
        self.on_token_refreshed = on_token_refreshed

    def _is_token_valid(self) -> bool:
        if not self._access_token or not self._token_expires_at:
            return False
        return datetime.datetime.now() < self._token_expires_at

    def _get_headers(self) -> dict[str, str]:
        return {
            "accept": "*/*",
            "content-type": "application/json",
            "user-agent": self.USER_AGENT,
            "accept-language": "sv-SE;q=1.0, en-SE;q=0.9",
            "authorization": f"Bearer {self._access_token}",
        }

    def _request_token(self, payload: str) -> dict:
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": self.USER_AGENT,
            "accept-language": "sv-SE;q=1.0, en-SE;q=0.9",
        }
        response = requests.post(
            self.TOKEN_URL, data=payload, headers=headers, timeout=self.REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            raise InvalidTokenException(
                f"Failed to get token: {response.status_code} {response.text}"
            )
        return json.loads(response.text)

    def _process_token_response(self, response: dict) -> None:
        self._access_token = response["access_token"]
        self._refresh_token = response.get("refresh_token", self._refresh_token)
        expires_in = response["expires_in"]
        self._token_expires_at = datetime.datetime.now() + datetime.timedelta(
            seconds=expires_in - 60
        )
        if self.on_token_refreshed:
            self.on_token_refreshed(self._access_token, expires_in)

    def authenticate(self) -> None:
        if self._is_token_valid():
            return

        if self._refresh_token:
            try:
                payload = (
                    f"client_id={self.client_id}&client_secret={self.client_secret}"
                    f"&grant_type=refresh_token&refresh_token={self._refresh_token}"
                )
                response = self._request_token(payload)
                self._process_token_response(response)
                return
            except InvalidTokenException:
                pass

        query_string = urllib.parse.urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "password",
                "password": self.password,
                "username": self.username,
            }
        )
        response = self._request_token(query_string)
        self._process_token_response(response)

    def _ensure_authenticated(self) -> None:
        if not self._is_token_valid():
            self.authenticate()

    def get_status(self) -> CtekDeviceInfo:
        self._ensure_authenticated()
        url = f"{self.BASE_URL}/devices/{self.device_id}/status"
        response = requests.get(
            url, headers=self._get_headers(), timeout=self.REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            self._handle_error(response)
        data = json.loads(response.text)
        connectors = []
        for c in data.get("connectors", []):
            connectors.append(
                CtekConnectorInfo(
                    id=c["id"],
                    device_id=c["deviceId"],
                    current_status=c["currentStatus"],
                    status_reason=c.get("statusReason", ""),
                    status_string=c.get("statusString", ""),
                    status=c["status"],
                )
            )
        return CtekDeviceInfo(
            device_id=data["deviceId"],
            device_name=data.get("device_name", ""),
            connectors=connectors,
            connected=data.get("connected", False),
        )

    def set_enable_charging(self, enable: bool) -> None:
        self._ensure_authenticated()
        url = f"{self.BASE_URL}/api/v3/device/control"
        payload = {
            "device_id": self.device_id,
            "instruction": "RESUME_CHARGING" if enable else "PAUSE_CHARGING",
            "connector_id": 1,
        }
        response = requests.post(
            url, json=payload, headers=self._get_headers(), timeout=self.REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            self._handle_error(response)

    def set_max_current(self, current_limit: int) -> None:
        if current_limit not in CURRENT_LIMITS:
            raise ValueError(
                f"Invalid current value: {current_limit}. Must be one of {CURRENT_LIMITS}"
            )
        self._ensure_authenticated()
        url = f"{self.BASE_URL}/api/v3/device/configurations"
        payload = {"CurrentMaxAssignment": str(current_limit)}
        response = requests.post(
            url,
            json=payload,
            headers=self._get_headers(),
            params={"deviceId": self.device_id, "pushToDevice": "true"},
            timeout=self.REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            self._handle_error(response)

    def delete_all_schedules(self) -> None:
        self._ensure_authenticated()
        url = f"{self.BASE_URL}/schedule/transactions"
        response = requests.delete(
            url,
            headers=self._get_headers(),
            params={"deviceId": self.device_id},
            timeout=self.REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            self._handle_error(response)

    def _handle_error(self, response: requests.Response) -> None:
        try:
            err = json.loads(response.text)
            if err.get("error") == "invalid_token":
                self._access_token = None
                self._token_expires_at = None
                self.authenticate()
                raise InvalidTokenException("Token invalid, re-authenticated")
            raise Exception(f"CTEK API error: {err}")
        except (json.JSONDecodeError, KeyError):
            raise Exception(f"CTEK API error: {response.status_code} {response.text}")

    @property
    def access_token(self) -> Optional[str]:
        return self._access_token

    @property
    def refresh_token(self) -> Optional[str]:
        return self._refresh_token

    @property
    def token_expires_at(self) -> Optional[datetime.datetime]:
        return self._token_expires_at


@dataclass
class ZaptecSettings:
    username: str
    password: str
    installation_id: str
    charger_id: str
    access_token: Optional[str] = None
    token_expires_at: Optional[str] = None
    on_token_refreshed: Optional[Callable[[str, int], None]] = None
    base_url: Optional[str] = None


@dataclass
class CtekSettings:
    client_id: str
    client_secret: str
    username: str
    password: str
    device_id: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[str] = None
    on_token_refreshed: Optional[Callable[[str, int], None]] = None


class ZaptecCharger(BaseCharger):
    """Zaptec charger implementation.

    - `settings` contains credentials and installation id (kept as a normal field so
      it can be configured/validated externally).
    - `_client` is a runtime-only attribute and excluded from Pydantic schema via
      `PrivateAttr`.
    - `model_post_init` (pydantic v2 lifecycle hook) is used to create and
      authenticate the ZaptecClient after the model is initialized.
    """

    settings: ZaptecSettings
    _client: Optional[ZaptecClient] = PrivateAttr(None)

    def model_post_init(self, __context):
        token_expires_at = None
        if self.settings.token_expires_at:
            token_expires_at = datetime.datetime.fromisoformat(
                self.settings.token_expires_at
            )

        self._client = ZaptecClient(
            initial_access_token=self.settings.access_token,
            token_expires_at=token_expires_at,
            on_token_refreshed=self.settings.on_token_refreshed,
        )

        self._client.authenticate(
            username=self.settings.username, password=self.settings.password
        )

    def charger_type(self) -> ChargerType:
        return ChargerType.ZAPTEC

    def set_current(self, current: float) -> None:
        super().set_current(current)
        logger.info("Set current to %s A on Zaptec charger %s", current, self.id)
        if self.read_only:
            logger.info("Read-only mode: skipping actual current update")
            return
        if self._client is not None:
            try:
                self._client.update_installation(
                    installation_id=self.settings.installation_id,
                    available_current=current,
                )
            except Exception as e:
                if "scheduled power management" in str(e).lower():
                    logger.warning(
                        "Cannot update installation current: Zaptec is in scheduled power management mode. "
                        "Skipping current adjustment."
                    )
                else:
                    logger.exception("Failed to update Zaptec installation current")

    def start_charging(self) -> None:
        super().start_charging()
        logger.info("Starting Zaptec charger ID: %s", self.id)
        if self.read_only:
            logger.info("Read-only mode: skipping actual start command")
            return
        try:
            current_status = self.get_status()
            if current_status == OperatingMode.Connected_Charging:
                logger.info(
                    "Charger %s is already charging, skipping START command", self.id
                )
                return
            self._client.send_charger_command(
                charger_id=self.settings.charger_id, command_id=ChargerCommands.START
            )
        except Exception:
            logger.exception("Failed to start charging")

    def stop_charging(self) -> None:
        super().stop_charging()
        logger.info("Stopping Zaptec charger ID: %s", self.id)
        if self.read_only:
            logger.info("Read-only mode: skipping actual stop command")
            return
        try:
            self._client.send_charger_command(
                charger_id=self.settings.charger_id, command_id=ChargerCommands.STOP
            )
        except Exception:
            logger.exception("Failed to stop charging")

    def get_status(self) -> OperatingMode:
        details = self._client.get_charger_details(charger_id=self.settings.charger_id)
        op_mode = details.operating_mode
        return OperatingMode(op_mode)

    @staticmethod
    def map_status(status: str) -> Optional[ChargerStatus]:
        operating_mode = OperatingMode.from_name(status)
        if operating_mode == OperatingMode.Disconnected:
            return ChargerStatus.DISCONNECTED
        elif operating_mode in [OperatingMode.Connected_Requesting]:
            return ChargerStatus.CONNECTED
        elif operating_mode == OperatingMode.Connected_Charging:
            return ChargerStatus.CHARGING
        elif operating_mode == OperatingMode.Connected_Finished:
            return ChargerStatus.FINISHED
        else:
            return None

    @staticmethod
    def get_connected_from_status(status: str) -> bool:
        operating_mode = OperatingMode.from_name(status)
        return operating_mode in [
            OperatingMode.Connected_Requesting,
            OperatingMode.Connected_Charging,
            OperatingMode.Connected_Finished,
        ]

    @staticmethod
    def get_charging_from_status(status: str) -> bool:
        operating_mode = OperatingMode.from_name(status)
        return operating_mode == OperatingMode.Connected_Charging


class CtekCharger(BaseCharger):
    """CTEK charger implementation.

    - `settings` contains CTEK credentials and device id.
    - `_client` is a runtime-only attribute excluded from Pydantic schema via `PrivateAttr`.
    - `model_post_init` creates and authenticates the CtekClient after initialization.
    """

    settings: CtekSettings
    _client: Optional[CtekClient] = PrivateAttr(None)

    def model_post_init(self, __context) -> None:
        token_expires_at = None
        if self.settings.token_expires_at:
            token_expires_at = datetime.datetime.fromisoformat(
                self.settings.token_expires_at
            )

        self._client = CtekClient(
            client_id=self.settings.client_id,
            client_secret=self.settings.client_secret,
            username=self.settings.username,
            password=self.settings.password,
            device_id=self.settings.device_id,
            access_token=self.settings.access_token,
            refresh_token=self.settings.refresh_token,
            token_expires_at=token_expires_at,
            on_token_refreshed=self.settings.on_token_refreshed,
        )
        self._client.authenticate()

    def charger_type(self) -> ChargerType:
        return ChargerType.CTEK

    def set_current(self, current: float) -> None:
        super().set_current(current)
        logger.info("Set current to %s A on CTEK charger %s", current, self.id)
        if self.read_only:
            logger.info("Read-only mode: skipping actual current update")
            return
        if self._client is not None and current != 0:
            try:
                self._client.set_max_current(int(current))
            except Exception:
                logger.exception("Failed to set CTEK max current")

    def start_charging(self) -> None:
        super().start_charging()
        logger.info("Starting CTEK charger ID: %s", self.id)
        if self.read_only:
            logger.info("Read-only mode: skipping actual start command")
            return
        try:
            current_status = self.get_status()
            if current_status == OperatingMode.Connected_Charging:
                logger.info(
                    "Charger %s is already charging, skipping START command", self.id
                )
                return
            if self._client is not None:
                self._client.set_enable_charging(True)
        except Exception:
            logger.exception("Failed to start CTEK charging")

    def stop_charging(self) -> None:
        super().stop_charging()
        logger.info("Stopping CTEK charger ID: %s", self.id)
        if self.read_only:
            logger.info("Read-only mode: skipping actual stop command")
            return
        try:
            if self._client is not None:
                self._client.set_enable_charging(False)
        except Exception:
            logger.exception("Failed to stop CTEK charging")

    def get_status(self) -> OperatingMode:
        if self._client is None:
            return OperatingMode.Disconnected
        device_info = self._client.get_status()
        if not device_info.connectors:
            return OperatingMode.Disconnected
        connector = device_info.connectors[0]
        ctek_mode = CtekOperatingMode.from_connector_status(connector.current_status)
        return ctek_mode.to_operating_mode()

    @staticmethod
    def map_status(status: str) -> Optional[ChargerStatus]:
        ctek_mode = CtekOperatingMode.from_connector_status(status)
        operating_mode = ctek_mode.to_operating_mode()
        if operating_mode == OperatingMode.Disconnected:
            return ChargerStatus.DISCONNECTED
        elif operating_mode == OperatingMode.Connected_Requesting:
            return ChargerStatus.CONNECTED
        elif operating_mode == OperatingMode.Connected_Charging:
            return ChargerStatus.CHARGING
        elif operating_mode == OperatingMode.Connected_Finished:
            return ChargerStatus.FINISHED
        return None

    @staticmethod
    def get_connected_from_status(status: str) -> bool:
        ctek_mode = CtekOperatingMode.from_connector_status(status)
        return ctek_mode not in (
            CtekOperatingMode.Disconnected,
            CtekOperatingMode.Error,
            CtekOperatingMode.Unknown,
        )

    @staticmethod
    def get_charging_from_status(status: str) -> bool:
        ctek_mode = CtekOperatingMode.from_connector_status(status)
        return ctek_mode == CtekOperatingMode.Connected_Charging
