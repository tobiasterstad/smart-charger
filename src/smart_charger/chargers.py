import abc
import enum
import logging
from dataclasses import dataclass
from pydantic import BaseModel, PrivateAttr
from smart_charger.config import ChargerType
from smart_charger.zaptec import ZaptecClient, ChargerCommands, OperatingMode
from typing import Callable, Optional

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
    def start_charging(self):
        self.status = ChargerStatus.CHARGING

    @abc.abstractmethod
    def stop_charging(self):
        self.status = ChargerStatus.CONNECTED

    @abc.abstractmethod
    def set_current(self, current: float):
        # Accept either 0 (off) or values in the 6..16 A range
        if current != 0 and not (6 <= current <= 16):
            raise ValueError("Current must be 0 or between 6 and 16 A")
        self.current = current

    @abc.abstractmethod
    def get_status(self) -> OperatingMode:
        raise NotImplementedError

    @staticmethod
    def map_status(status: str):
        raise NotImplementedError

    @staticmethod
    @abc.abstractmethod
    def get_connected_from_status(status: str):
        raise NotImplementedError

    @staticmethod
    @abc.abstractmethod
    def get_charging_from_status(status: str):
        raise NotImplementedError


# Small dataclass to hold Zaptec credentials and options. This keeps secrets out of
# your code and makes it easy to create settings objects in tests.


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
        import datetime

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

    def set_current(self, current: float):
        # call base validation
        super().set_current(current)
        logger.info("Set current to %s A on Zaptec charger %s", current, self.id)
        if self.read_only:
            logger.info("Read-only mode: skipping actual current update")
            return
        # use the client if available; tolerate missing client for tests/mocks
        if self._client is not None:
            try:
                self._client.update_installation(
                    installation_id=self.settings.installation_id,
                    available_current=current,
                )
            except Exception:
                logger.exception("Failed to update Zaptec installation current")

    def start_charging(self):
        super().start_charging()
        logger.info(f"Starting Zaptec charger ID: {self.id}")
        if self.read_only:
            logger.info("Read-only mode: skipping actual start command")
            return
        try:
            self._client.send_charger_command(
                charger_id=self.settings.charger_id, command_id=ChargerCommands.START
            )
        except Exception as e:
            logger.exception("Failed to start charging", e)

    def stop_charging(self):
        super().stop_charging()
        logger.info(f"Stopping Zaptec charger ID: {self.id}")
        if self.read_only:
            logger.info("Read-only mode: skipping actual stop command")
            return
        try:
            self._client.send_charger_command(
                charger_id=self.settings.charger_id, command_id=ChargerCommands.STOP
            )
        except Exception as e:
            logger.exception("Failed to start charging", e)

    def get_status(self) -> OperatingMode:
        details = self._client.get_charger_details(charger_id=self.settings.charger_id)
        op_mode = details.operating_mode
        return OperatingMode(op_mode)

    @staticmethod
    def map_status(status: str):
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
    def get_connected_from_status(status: str):
        operating_mode = OperatingMode.from_name(status)
        return operating_mode in [
            OperatingMode.Connected_Requesting,
            OperatingMode.Connected_Charging,
            OperatingMode.Connected_Finished,
        ]

    @staticmethod
    def get_charging_from_status(status: str):
        operating_mode = OperatingMode.from_name(status)
        return operating_mode == OperatingMode.Connected_Charging


class CtekCharger(BaseCharger):
    @staticmethod
    def get_connected_from_status(status: str):
        pass

    def get_charging_from_status(self, status: str):
        pass

    def get_status(self) -> OperatingMode:
        # not implemented
        pass

    # no custom __init__ — rely on BaseModel init (pass id=<...> when instantiating)

    def charger_type(self) -> ChargerType:
        return ChargerType.CTEK

    def set_current(self, current: float):
        super().set_current(current)
        logger.info("Set current to %s A on CTEK charger %s", current, self.id)

    def start_charging(self):
        logger.info("Starting CTEK charger")

    def stop_charging(self):
        logger.info("Stopping CTEK charger")
