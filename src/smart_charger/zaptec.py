import datetime
import enum
import logging
from typing import Callable, Optional

import requests
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    scope: Optional[str] = None
    refresh_token: Optional[str] = None


# Installation
class Installation(BaseModel):
    Id: str
    Name: str
    Address: str
    ZipCode: str
    City: str
    CountryId: str
    InstallationType: int
    MaxCurrent: float
    AvailableCurrent: float
    AvailableCurrentPhase1: float
    AvailableCurrentPhase2: float
    AvailableCurrentPhase3: float
    AvailableCurrentMode: int
    AvailableCurrentScheduleWeekendActive: bool
    DefaultThreeToOneSwitchCurrent: float
    InstallationCategoryId: str
    InstallationCategory: str
    UseLoadBalancing: bool
    IsRequiredAuthentication: bool
    Latitude: float
    Longitude: float
    Active: bool
    NetworkType: int
    AvailableInternetAccessPLC: bool
    AvailableInternetAccessWiFi: bool
    CreatedOnDate: str
    UpdatedOn: str
    CurrentUserRoles: int
    AuthenticationType: int
    MessagingEnabled: bool
    RoutingId: str
    OcppCloudUrlVersion: int
    IsSubscriptionsAvailableForCurrentUser: bool
    AvailableFeatures: int
    EnabledFeatures: int
    PropertyFirmwareAutomaticUpdates: bool

    @staticmethod
    def get_default_installation_id() -> str:
        return "2afb9e8a-4027-4f43-b296-42986511301d"


class Installations(BaseModel):
    Pages: int
    Data: list[Installation]


class ChargerCommands(enum.Enum):
    RESTART = 102
    UPGRADE_FIRMWARE = 200
    STOP = 506
    START = 507
    DEAUTH = 10001


class ChargerState(BaseModel):
    charger_id: str = Field(alias="chargerId")
    state_id: int = Field(alias="stateId")
    state_name: Optional[str] = Field(alias="stateName")
    timestamp: datetime.datetime = Field(alias="timestamp")
    value: Optional[str] = Field(alias="valueAsString")


class ChargerStateResponse(BaseModel):
    states: list[ChargerState] = Field(alias="")


class ChargerDetail(BaseModel):
    id: str = Field(alias="Id")
    device_id: str = Field(alias="DeviceId")
    name: str = Field(alias="Name")
    active: bool = Field(alias="Active")
    current_user_roles: int = Field(alias="CurrentUserRoles")
    pin: int = Field(alias="Pin")
    has_sessions: bool = Field(alias="HasSessions")
    signed_meter_value_kwh: float = Field(alias="SignedMeterValueKwh")
    signed_meter_value: str = Field(alias="SignedMeterValue")
    operating_mode: int = Field(alias="OperatingMode")
    is_online: bool = Field(alias="IsOnline")
    warnings: Optional[str] = Field(alias="Warnings", default=None)


class OperatingMode(enum.Enum):
    Unknown = 0
    Disconnected = 1
    Connected_Requesting = 2
    Connected_Charging = 3
    Connected_Finished = 5

    @staticmethod
    def from_name(name: Optional[str]):
        """Return the OperatingMode matching the provided name.

        Matching is case-insensitive and ignores non-alphanumeric characters
        (spaces, underscores, dashes, dots). If the input is a numeric string
        matching an enum value, that enum member is returned. If no match is
        found, OperatingMode.Unknown is returned.
        """
        if not name:
            return OperatingMode.Unknown

        def normalize(s: str) -> str:
            return "".join(ch for ch in s.lower() if ch.isalnum())

        norm = normalize(name)

        # Direct name match after normalization
        for member in OperatingMode:
            if normalize(member.name) == norm:
                return member

        # If the provided name is numeric, try to match by value
        if norm.isdigit():
            try:
                val = int(norm)
                for member in OperatingMode:
                    if member.value == val:
                        return member
            except ValueError:
                pass

        # Fallback: substring containment (rare), e.g. 'charging' -> Connected_Charging
        for member in OperatingMode:
            if norm in normalize(member.name):
                return member

        return OperatingMode.Unknown


class ZaptecClient:
    def __init__(
        self,
        initial_access_token: Optional[str] = None,
        token_expires_at: Optional[datetime.datetime] = None,
        on_token_refreshed: Optional[Callable[[str, int], None]] = None,
    ):
        self.access_token: Optional[str] = initial_access_token
        self._token_expires_at: Optional[datetime.datetime] = token_expires_at
        self._on_token_refreshed = on_token_refreshed
        self._username: Optional[str] = None
        self._password: Optional[str] = None

    def authenticate(
        self,
        username: str,
        password: str,
    ) -> str:
        self._username = username
        self._password = password

        if (
            self.access_token
            and self._token_expires_at
            and datetime.datetime.now() < self._token_expires_at
        ):
            logger.info("Using cached access token")
            return self.access_token

        logger.info("Attempting password authentication")
        token_response = self._get_access_token(
            username,
            password,
            token_url="https://api.zaptec.com/oauth/token",
        )
        logger.info("Token response: expires_in=%s", token_response.expires_in)
        self.access_token = token_response.access_token
        self._token_expires_at = datetime.datetime.now() + datetime.timedelta(
            seconds=token_response.expires_in - 60
        )
        logger.info("Password authentication successful")

        if self._on_token_refreshed:
            self._on_token_refreshed(self.access_token, token_response.expires_in)

        return self.access_token

    def _ensure_valid_token(self) -> None:
        if (
            not self.access_token
            or not self._token_expires_at
            or datetime.datetime.now() >= self._token_expires_at
        ):
            if not self._username or not self._password:
                raise Exception("Not authenticated and no credentials available")
            logger.info("Token expired, re-authenticating")
            self.authenticate(self._username, self._password)

    @staticmethod
    def _get_access_token(
        username: str,
        password: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        token_url: str = "https://api.zaptec.com/oauth/token",
        timeout: int = 10,
    ) -> TokenResponse:
        """Request an OAuth token using the Resource Owner Password Credentials grant.

        The request is sent as application/x-www-form-urlencoded (requests `data=`),
        not JSON. Returns the parsed JSON response from the token endpoint.

        Args:
            username: The user's username.
            password: The user's password.
            client_id: Optional client_id to include in the form.
            client_secret: Optional client_secret to include in the form.
            token_url: OAuth token endpoint.
            timeout: Request timeout in seconds.

        Raises:
            requests.HTTPError: If the response has an HTTP error status.
            requests.RequestException: For other transport errors.
            ValueError: If required credentials are missing.
        """
        if not username or not password:
            raise ValueError(
                "username and password are required to obtain an access token"
            )

        data = {
            "grant_type": "password",
            "username": username,
            "password": password,
        }

        if client_id:
            data["client_id"] = client_id
        if client_secret:
            data["client_secret"] = client_secret

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            response = requests.post(
                token_url, data=data, headers=headers, timeout=timeout
            )
            response.raise_for_status()
        except requests.HTTPError as e:
            logger.error("OAuth request failed: %s - %s", e, response.text)
            raise

        return TokenResponse.model_validate_json(response.text)

    @staticmethod
    def _refresh_token(
        refresh_token: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        token_url: str = "https://api.zaptec.com/oauth/token",
        timeout: int = 10,
    ) -> TokenResponse:
        """Request a new access token using a refresh token.

        Args:
            refresh_token: The refresh token.
            client_id: Optional OAuth client ID.
            client_secret: Optional OAuth client secret.
            token_url: OAuth token endpoint.
            timeout: Request timeout in seconds.

        Raises:
            requests.HTTPError: If the response has an HTTP error status.
            requests.RequestException: For other transport errors.
        """
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        if client_id:
            data["client_id"] = client_id
        if client_secret:
            data["client_secret"] = client_secret

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        response = requests.post(token_url, data=data, headers=headers, timeout=timeout)

        response.raise_for_status()
        return TokenResponse.model_validate_json(response.text)

    def get_installations(self):
        self._ensure_valid_token()
        url = "https://api.zaptec.com/api/installation"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }
        response = requests.get(url, headers=headers)
        return Installations.model_validate_json(response.text)

    def update_installation(
        self, installation_id: str, available_current: float
    ) -> None:
        self._ensure_valid_token()
        url = f"https://api.zaptec.com/api/installation/{installation_id}/update"
        headers = {
            "accept": "application/json",
            "content-type": "application/*+json",
            "Authorization": f"Bearer {self.access_token}",
        }
        body = {
            "AvailableCurrent": available_current,
        }
        response = requests.post(url, json=body, headers=headers)
        if response.status_code != 200:
            error_details = response.text
            raise Exception(
                f"Failed to update installation: {response.status_code} {error_details}"
            )

    def get_charger_details(self, charger_id: str) -> ChargerDetail:
        self._ensure_valid_token()
        url = f"https://api.zaptec.com/api/chargers/{charger_id}"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }
        response = requests.get(url, headers=headers)
        response_text = response.text
        if response.status_code != 200:
            raise Exception(
                f"Failed to get charger details: {response.status_code} {response_text}"
            )
        return ChargerDetail.model_validate_json(response_text)

    def get_charger_state(self, charger_id: str) -> ChargerStateResponse:
        self._ensure_valid_token()
        url = f"https://api.zaptec.com/api/chargers/{charger_id}/state"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }
        response = requests.get(url, headers=headers)
        response_text = response.text
        if response.status_code != 200:
            raise Exception(
                f"Failed to get charger details: {response.status_code} {response_text}"
            )
        return ChargerStateResponse.model_validate_json(response_text)

    def update_charger(self, charger_id: str, max_current: float) -> None:
        self._ensure_valid_token()
        url = f"https://api.zaptec.com/api/chargers/{charger_id}/update"
        headers = {
            "content-type": "application/*+json",
            "Authorization": f"Bearer {self.access_token}",
        }
        body = {"maxChargeCurrent": max_current}
        response = requests.post(url, json=body, headers=headers)
        if response.status_code != 200:
            raise Exception(
                f"Failed to update charger: {response.status_code} {response.text}"
            )

    def send_charger_command(
        self, charger_id: str, command_id: ChargerCommands
    ) -> None:
        self._ensure_valid_token()
        url = f"https://api.zaptec.com/api/chargers/{charger_id}/sendCommand/{command_id.value}"
        headers = {
            "content-type": "application/*+json",
            "Authorization": f"Bearer {self.access_token}",
        }
        response = requests.post(url, headers=headers)
        if response.status_code != 200:
            raise Exception(
                f"Failed to update charger: {response.status_code} {response.text}"
            )
