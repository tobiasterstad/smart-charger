import enum
from typing import Optional

from pydantic import BaseModel

from smart_charger.tariff import WinterPeak1, GenericTariffConfig


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
    topic_prefix: Optional[str] = None


class PlannerType(enum.Enum):
    SIMPLE = 1
    TIBBER = 2


class ChargerConfiguration(BaseModel):
    mqtt_broker: str
    mqtt_port: int
    smart_charger_topic_prefix: str
    vehicles: list[VehicleConfig] = []
    chargers: list[ChargerConfig] = []
    tariff: GenericTariffConfig
    high_load_topic: Optional[str] = None
    high_load_threshold: Optional[float] = None
    high_hourly_energy_threshold: Optional[float] = None
    high_hourly_energy_topic: Optional[str] = None
    power_consumption_topic: Optional[str] = None
    power_production_topic: Optional[str] = None
    power_accumulated_hourly_topic: Optional[str] = None
    planner: PlannerType = PlannerType.SIMPLE
    solar_surplus_charging: bool = True
    solar_min_excess_watts: float = 1500
    solar_max_effective_price: float = 0.15
    solar_min_current_amps: int = 6
    solar_charge_interval_minutes: int = 15

    @staticmethod
    def load_defaults():
        config = ChargerConfiguration(
            mqtt_broker="10.100.0.10",
            mqtt_port=1883,
            smart_charger_topic_prefix="terstad/smartcharger",
            high_load_threshold=4000,
            high_hourly_energy_threshold=5.0,
            high_hourly_energy_topic="terstad/energy/high_accumulated_hour_consumption",
            tariff=WinterPeak1(topic="terstad/energy/tariff"),
            planner=PlannerType.TIBBER,
        )
        config.chargers = [
            ChargerConfig(
                id="ctek_charger_1",
                name="Ctek Charger",
                type=ChargerType.CTEK,
                connected_topic="terstad/smartcharger/chargers/ctek/connected",
                status_topic="terstad/smartcharger/chargers/ctek/status",
            ),
            ChargerConfig(
                id="gpn018087",
                name="Zaptec Charger",
                type=ChargerType.ZAPTEC,
                connected_topic="terstad/smartcharger/chargers/gpn018087/connected",
                status_topic="terstad/smartcharger/chargers/gpn018087/status",
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
        config.power_accumulated_hourly_topic = (
            "terstad/energy/accumulated_hour_consumption"
        )
        return config

    def get_vehicle_config_by_id(self, vehicle_id: str) -> Optional[VehicleConfig]:
        for vehicle in self.vehicles:
            if vehicle.id == vehicle_id:
                return vehicle
        return None
