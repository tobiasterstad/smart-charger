from pydantic import BaseModel


class VehicleStatus(BaseModel):
    id: str = ""
    soc: int = 0
    connected: bool = False
