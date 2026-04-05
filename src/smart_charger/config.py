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
    status_topic: Optional[str] = None

    def build_topics(self, prefix: str) -> str:
        return f"{prefix}/chargers/{self.id}/status"

    def get_outgoing_status_topic(self, prefix: str) -> str:
        return f"{prefix}/chargers/{self.id.lower()}/status"

    def get_outgoing_current_topic(self, prefix: str) -> str:
        return f"{prefix}/chargers/{self.id.lower()}/current"


class VehicleConfig(BaseModel):
    id: str
    name: str
    target_soc: int = 80
    capacity_kwh: Optional[float] = None
    soc_topic: Optional[str] = None
    status_topic: Optional[str] = None
    enabled: bool = True

    def build_topics(self, prefix: str) -> tuple[str, str]:
        return (
            f"{prefix}/vehicles/{self.id}/status",
            f"{prefix}/vehicles/{self.id}/soc",
        )

    def get_outgoing_status_topic(self, prefix: str) -> str:
        return f"{prefix}/vehicles/{self.id.lower()}/status"

    def get_outgoing_soc_topic(self, prefix: str) -> str:
        return f"{prefix}/vehicles/{self.id.lower()}/soc"


class PlannerType(enum.Enum):
    SIMPLE = 1
    TIBBER = 2


class ChargerConfiguration(BaseModel):
    mqtt_broker: str
    mqtt_port: int
    device_topic_prefix: str = "devices"
    smart_charger_topic_prefix: str = "smartcharger"
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
            device_topic_prefix="terstad/devices",
            smart_charger_topic_prefix="terstad/smartcharger",
            high_load_threshold=4000,
            high_hourly_energy_threshold=5.0,
            high_hourly_energy_topic="terstad/energy/high_accumulated_hour_consumption",
            tariff=WinterPeak1(topic="terstad/energy/tariff"),
            planner=PlannerType.TIBBER,
        )
        ctek_status = ChargerConfig(
            id="ctek_charger_1",
            name="Ctek Charger",
            type=ChargerType.CTEK,
        ).build_topics(config.device_topic_prefix)
        zaptec_status = ChargerConfig(
            id="gpn018087",
            name="Zaptec Charger",
            type=ChargerType.ZAPTEC,
        ).build_topics(config.device_topic_prefix)
        config.chargers = [
            ChargerConfig(
                id="ctek_charger_1",
                name="Ctek Charger",
                type=ChargerType.CTEK,
                status_topic=ctek_status,
            ),
            ChargerConfig(
                id="gpn018087",
                name="Zaptec Charger",
                type=ChargerType.ZAPTEC,
                status_topic=zaptec_status,
            ),
        ]
        leaf_status, leaf_soc = VehicleConfig(
            id="leaf",
            name="Nissan Leaf",
            capacity_kwh=40,
            target_soc=80,
        ).build_topics(config.device_topic_prefix)
        rav4_status, rav4_soc = VehicleConfig(
            id="rav4",
            name="Toyota RAV4",
            capacity_kwh=18,
            target_soc=100,
        ).build_topics(config.device_topic_prefix)
        config.vehicles = [
            VehicleConfig(
                id="leaf",
                name="Nissan Leaf",
                capacity_kwh=40,
                target_soc=80,
                status_topic=leaf_status,
                soc_topic=leaf_soc,
            ),
            VehicleConfig(
                id="rav4",
                name="Toyota RAV4",
                capacity_kwh=18,
                target_soc=100,
                status_topic=rav4_status,
                soc_topic=rav4_soc,
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

    def get_charger_config_by_id(self, charger_id: str) -> Optional[ChargerConfig]:
        for charger in self.chargers:
            if charger.id == charger_id:
                return charger
        return None
