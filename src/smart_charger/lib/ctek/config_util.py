import configparser
import os
import logging

from pydantic.dataclasses import dataclass
from typing import Optional

import yaml


@dataclass
class VehicleData:
    id: str
    name: str
    type: str
    battery_capacity_kwh: float
    target_soc: int
    soc_mqtt_topic: str
    connected_mqtt_topic: str
    soc: Optional[int] = None

@dataclass
class TibberConfig:
    api_key: str

@dataclass
class CTEKConfig:
    client_id: str
    client_secret: str
    username: str
    password: str
    device_id: str

@dataclass
class MQTTConfig:
    broker: str
    port: str
    username: str
    password: str
    client_id: str
    topic_prefix: str

@dataclass
class EnergyConfig:
    grid_production_topic: str
    grid_consumption_topic: str
    solar_production_topic: str

@dataclass
class ChargerData:
    device_id: str
    energy: EnergyConfig
    vehicles: list[VehicleData]
    tibber: TibberConfig
    ctek: CTEKConfig
    mqtt: MQTTConfig
    charging_hours: int = 5

@dataclass
class ConfigData:
    charger: ChargerData
    description: Optional[str] = None

@dataclass
class CredentialsCache:
    access_token: str = ""
    refresh_token: str = ""
    token_expires: int = 0

class ConfigUtil:

    config_data: ConfigData

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            self.config_path = os.path.join(os.path.expanduser("~"), ".ctek")
            self.config_file_path_yaml = os.path.join(self.config_path, "config.yaml")
            self.credentials_cache_file_path = os.path.join(self.config_path, "credentials_cache.yaml")
            if not os.path.isdir(self.config_path):
                os.mkdir(self.config_path)
        else:
            self.config_file_path_yaml = os.path.join(config_path, "config.yaml")
            self.credentials_cache_file_path = os.path.join(config_path, "credential_cache.yaml")

        self.config = configparser.ConfigParser()
        self.logger = logging.getLogger(__name__)

    def get_config(self) -> ConfigData:
        with open(self.config_file_path_yaml, 'r') as file:
            yaml_data = yaml.safe_load(file.read())
            return ConfigData(**yaml_data)

    def get_credentials_cache(self) -> CredentialsCache:
        if not os.path.isfile(self.credentials_cache_file_path):
            with open(self.credentials_cache_file_path, 'w') as file:
                # Create an empty credentials cache file if it does not exist
                yaml.dump(CredentialsCache().__dict__, file)

        with open(self.credentials_cache_file_path, 'r') as file:
            yaml_data = yaml.safe_load(file.read())
            return CredentialsCache(**yaml_data)

    def save_credentials_cache(self, cache: CredentialsCache):
        # Save the updated credentials cache file, preserving formatting, comments, and empty lines
        with open(self.credentials_cache_file_path, 'w') as file:
            yaml.dump(cache.__dict__, file)
