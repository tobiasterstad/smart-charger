import enum
from typing import Optional

from pydantic import BaseModel

class ChargerType(enum.Enum):
    CTEK = "ctek"
    ZAPTEC = "zaptec"


class ChargerConfig(BaseModel):
    id: str
    name: str
    type: ChargerType
    connected_topic: Optional[str]
    status_topic: Optional[str]

class VehicleConfig(BaseModel):
    id: str
    name: str
    target_soc: int = 80
    capacity_kwh: Optional[float] = None
    soc_topic: Optional[str] = None
    connected_topic: Optional[str] = None
    enabled: bool = True
    topic_prefix: str = None

class TariffConfig(BaseModel):
    topic: str
    model: str = "3-peeks"
    months: list[int] = [1, 2, 3, 10, 11, 12]
    days: list[int] = [0, 1, 2, 3, 4, 5, 6]  # 0=Monday, 6=Sunday
    hours: list[int] = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]

class ChargerConfiguration(BaseModel):
    mqtt_broker: str
    mqtt_port: int
    smart_charger_topic_prefix: str
    vehicles: list[VehicleConfig] = []
    chargers: list[ChargerConfig] = []
    tariff: TariffConfig
    high_load_topic: Optional[str] = None
    high_load_threshold: Optional[float] = None
    power_consumption_topic: Optional[str] = None
    power_production_topic: Optional[str] = None

    @staticmethod
    def load_defaults():
        config = ChargerConfiguration(
            mqtt_broker="10.100.0.10",
            mqtt_port=1883,
            smart_charger_topic_prefix="terstad/smartcharger",
            high_load_threshold=4000,
            tariff=TariffConfig(topic="terstad/energy/tariff")
        )
        config.chargers = [
            ChargerConfig(
                id="ctek_charger_1",
                name="Ctek Charger",
                type=ChargerType.CTEK,
                connected_topic="terstad/smartcharger/chargers/ctek/connected",
                status_topic="terstad/smartcharger/chargers/ctek/status"
            ),
            ChargerConfig(
                id="GPN018087",
                name="Zaptec Charger",
                type=ChargerType.ZAPTEC,
                connected_topic="terstad/smartcharger/chargers/gpn018087/connected",
                status_topic="terstad/smartcharger/chargers/gpn018087/status"
            ),
        ]
        config.vehicles = [
            VehicleConfig(
                id="leaf",
                name="Nissan Leaf",
                capacity_kwh=40,
                target_soc=80,
                topic_prefix="terstad/vehicles",
                soc_topic="terstad/vehicles/leaf/soc",
                connected_topic="terstad/vehicles/leaf/connected",

            ),
            VehicleConfig(
                id="rav4",
                name="Toyota RAV4",
                capacity_kwh=18,
                target_soc=100,
                topic_prefix="terstad/vehicles",
                soc_topic="terstad/vehicles/rav4/soc",
                connected_topic="terstad/vehicles/rav4/connected",
            ),
        ]
        config.high_load_topic = "terstad/energy/high_load"
        config.power_consumption_topic = "terstad/energy/consumption"
        config.power_production_topic = "terstad/energy/production"
        return config

    def get_vehicle_config_by_id(self, vehicle_id: str) -> Optional[VehicleConfig]:
        for vehicle in self.vehicles:
            if vehicle.id == vehicle_id:
                return vehicle
        return None