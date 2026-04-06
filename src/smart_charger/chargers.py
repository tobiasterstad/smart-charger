import abc
import datetime
import enum
import logging
import time
from dataclasses import dataclass
from pydantic import BaseModel, PrivateAttr
from smart_charger.config import ChargerType
from smart_charger.zaptec import ZaptecClient, ChargerCommands, OperatingMode
from typing import Callable, Optional

logger = logging.getLogger(__name__)

SCHEDULED_POWER_MGMT_COOLDOWN_SECONDS = 300


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
    _scheduled_power_mgmt_cooldown_until: float = PrivateAttr(0.0)

    def _is_in_scheduled_power_mgmt_cooldown(self) -> bool:
        return time.time() < self._scheduled_power_mgmt_cooldown_until

    def _set_scheduled_power_mgmt_cooldown(self) -> None:
        self._scheduled_power_mgmt_cooldown_until = (
            time.time() + SCHEDULED_POWER_MGMT_COOLDOWN_SECONDS
        )

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

    def set_current(self, current: float):
        super().set_current(current)
        logger.info("Set current to %s A on Zaptec charger %s", current, self.id)
        if self.read_only:
            logger.info("Read-only mode: skipping actual current update")
            return
        if self._is_in_scheduled_power_mgmt_cooldown():
            logger.debug(
                "Skipping current update: in scheduled power management cooldown"
            )
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
                        "Skipping current adjustment for %s seconds.",
                        SCHEDULED_POWER_MGMT_COOLDOWN_SECONDS,
                    )
                    self._set_scheduled_power_mgmt_cooldown()
                else:
                    logger.exception("Failed to update Zaptec installation current")

    def start_charging(self):
        logger.info("Starting Zaptec charger ID: %s", self.id)
        if self.read_only:
            logger.info("Read-only mode: skipping actual start command")
            self.status = ChargerStatus.CHARGING
            return
        if self._is_in_scheduled_power_mgmt_cooldown():
            logger.debug(
                "Skipping start charging: in scheduled power management cooldown"
            )
            return
        try:
            current_status = self.get_status()
            if current_status == OperatingMode.Connected_Charging:
                logger.info(
                    "Charger %s is already charging, skipping START command", self.id
                )
                self.status = ChargerStatus.CHARGING
                return
            self._client.send_charger_command(
                charger_id=self.settings.charger_id, command_id=ChargerCommands.START
            )
            self.status = ChargerStatus.CHARGING
        except Exception as e:
            if "scheduled power management" in str(e).lower():
                logger.warning(
                    "Cannot start charging: Zaptec is in scheduled power management mode. "
                    "Skipping start command for %s seconds.",
                    SCHEDULED_POWER_MGMT_COOLDOWN_SECONDS,
                )
                self._set_scheduled_power_mgmt_cooldown()
            else:
                logger.exception("Failed to start charging")

    def stop_charging(self):
        logger.info("Stopping Zaptec charger ID: %s", self.id)
        if self.read_only:
            logger.info("Read-only mode: skipping actual stop command")
            self.status = ChargerStatus.CONNECTED
            return
        if self._is_in_scheduled_power_mgmt_cooldown():
            logger.debug(
                "Skipping stop charging: in scheduled power management cooldown"
            )
            return
        try:
            self._client.send_charger_command(
                charger_id=self.settings.charger_id, command_id=ChargerCommands.STOP
            )
            self.status = ChargerStatus.CONNECTED
        except Exception as e:
            if "scheduled power management" in str(e).lower():
                logger.warning(
                    "Cannot stop charging: Zaptec is in scheduled power management mode. "
                    "Skipping stop command for %s seconds.",
                    SCHEDULED_POWER_MGMT_COOLDOWN_SECONDS,
                )
                self._set_scheduled_power_mgmt_cooldown()
            else:
                logger.exception("Failed to stop charging")

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
