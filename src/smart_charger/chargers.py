import abc
import logging
from dataclasses import dataclass
from typing import Optional
from pydantic import BaseModel, PrivateAttr
from smart_charger.config import ChargerType
from smart_charger.zaptec import ZaptecClient, ChargerCommands, OperatingMode

logger = logging.getLogger(__name__)


class BaseCharger(abc.ABC, BaseModel):
    id: str
    connected: bool = False
    charging: bool = False
    current: float = 0

    @abc.abstractmethod
    def charger_type(self) -> ChargerType:
        raise NotImplementedError

    @abc.abstractmethod
    def start_charging(self):
        self.charging = True

    @abc.abstractmethod
    def stop_charging(self):
        self.charging = False

    @abc.abstractmethod
    def set_current(self, current: float):
        # Accept either 0 (off) or values in the 6..16 A range
        if current != 0 and not (6 <= current <= 16):
            raise ValueError("Current must be 0 or between 6 and 16 A")
        self.current = current

    @abc.abstractmethod
    def get_status(self) -> OperatingMode:
        raise NotImplementedError


# Small dataclass to hold Zaptec credentials and options. This keeps secrets out of
# your code and makes it easy to create settings objects in tests.
@dataclass
class ZaptecSettings:
    username: str
    password: str
    installation_id: str
    charger_id: str
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
        # Create the client and authenticate. Keep errors visible so callers can
        # handle failures (or tests can monkeypatch ZaptecClient).
        if self.settings.base_url:
            self._client = ZaptecClient()
        else:
            self._client = ZaptecClient()

        # authenticate; ZaptecClient should raise on auth failure
        self._client.authenticate(username=self.settings.username, password=self.settings.password)

    def charger_type(self) -> ChargerType:
        return ChargerType.ZAPTEC

    def set_current(self, current: float):
        # call base validation
        super().set_current(current)
        logger.info("Set current to %s A on Zaptec charger %s", current, self.id)
        # use the client if available; tolerate missing client for tests/mocks
        if self._client is not None:
            try:
                self._client.update_installation(installation_id=self.settings.installation_id, available_current=current)
            except Exception:
                logger.exception("Failed to update Zaptec installation current")

    def start_charging(self):
        super().start_charging()
        logger.info(f"Starting Zaptec charger ID: {self.id}")
        try:
            self._client.send_charger_command(charger_id=self.settings.charger_id, command_id=ChargerCommands.START)
        except Exception as e:
            logger.exception("Failed to start charging", e)

    def stop_charging(self):
        super().stop_charging()
        logger.info(f"Stopping Zaptec charger ID: {self.id}")
        try:
            self._client.send_charger_command(charger_id=self.settings.charger_id, command_id=ChargerCommands.STOP)
        except Exception as e:
            logger.exception("Failed to start charging", e)

    def get_status(self) -> OperatingMode:
        details = self._client.get_charger_details(charger_id=self.settings.charger_id)
        op_mode = details.operating_mode
        return OperatingMode(op_mode)


class CtekCharger(BaseCharger):
    def get_status(self) -> OperatingMode:
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

