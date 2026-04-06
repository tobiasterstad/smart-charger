import enum
from typing import Any
from pydantic import BaseModel, ConfigDict, model_validator


class VehicleConnectionStatus(enum.Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    CHARGING = "charging"


class VehicleStatus(BaseModel):
    model_config = ConfigDict(validate_by_alias=True)

    id: str = ""
    soc: int = 0
    connection_status: VehicleConnectionStatus = VehicleConnectionStatus.DISCONNECTED

    @model_validator(mode="before")
    @classmethod
    def convert_connected_to_status(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "connected" in values and "connection_status" not in values:
                if values["connected"]:
                    values["connection_status"] = VehicleConnectionStatus.CONNECTED
                else:
                    values["connection_status"] = VehicleConnectionStatus.DISCONNECTED
        return values

    @property
    def connected(self) -> bool:
        return self.connection_status in [
            VehicleConnectionStatus.CONNECTED,
            VehicleConnectionStatus.CHARGING,
        ]
