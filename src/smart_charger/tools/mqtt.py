from argparse import ArgumentParser
from paho.mqtt import client as mqtt_client
import logging

logger = logging.getLogger(__name__)

client_id = "smart-charger-client-mqtt"
port = 1883
broker = "10.100.0.10"

device_topic_prefix = "terstad/devices"
energy_topic_prefix = "terstad/energy"


def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to MQTT Broker!")
        else:
            logger.error("Failed to connect, return code %d\n", rc)

    client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION1, client_id)

    # client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.connect(broker, port)
    return client


def main():
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO
    )

    parser = ArgumentParser(
        description="MQTT message publisher for smart-charger testing"
    )
    parser.add_argument(
        "--connect-vehicle",
        type=str,
        help="Set vehicle connection status. Format: <vehicle_id>:<status> (e.g., leaf:connected, leaf:disconnected, leaf:charging)",
    )
    parser.add_argument(
        "--connect-charger",
        type=str,
        help="Simulate charger status. Format: <charger_id>:<status> (e.g., gpn018087:true, gpn018087:Connected_Requesting, gpn018087:Connected_Charging)",
    )
    parser.add_argument(
        "--update-soc",
        type=str,
        help="Update vehicle state of charge (SOC). Format: <vehicle_id>:<percentage> (e.g., leaf:80)",
    )
    parser.add_argument(
        "--production",
        type=int,
        help="Publish solar production in watts (e.g., --production 3500)",
    )
    parser.add_argument(
        "--consumption",
        type=int,
        help="Publish current power consumption in watts (e.g., --consumption 2500)",
    )
    args = parser.parse_args()

    client = connect_mqtt()

    if args.connect_charger:
        charger = args.connect_charger.split(":")[0]
        value = args.connect_charger.split(":")[1]
        valid_statuses = [
            "Connected_Requesting",
            "Connected_Charging",
            "Connected_Finished",
            "Disconnected",
        ]
        status = (
            value
            if value in valid_statuses
            else ("Connected_Requesting" if value == "true" else "Disconnected")
        )
        logger.info(f"Publishing charger status: {status}")
        client.publish(
            f"{device_topic_prefix}/chargers/{charger}/status",
            status,
        )
    elif args.connect_vehicle:
        vehicle = args.connect_vehicle.split(":")[0]
        value = args.connect_vehicle.split(":")[1]
        logger.info(f"Publishing vehicle status {value}")
        status = (
            value
            if value in ["connected", "disconnected", "charging"]
            else "disconnected"
        )
        client.publish(f"{device_topic_prefix}/vehicles/{vehicle}/status", status)
    elif args.update_soc:
        vehicle = args.update_soc.split(":")[0]
        soc = args.update_soc.split(":")[1]
        client.publish(f"{device_topic_prefix}/vehicles/{vehicle}/soc", soc)
    elif args.production is not None:
        logger.info(f"Publishing production {args.production} watts")
        client.publish(f"{energy_topic_prefix}/production", args.production)
    elif args.consumption is not None:
        logger.info(f"Publishing consumption {args.consumption} watts")
        client.publish(f"{energy_topic_prefix}/consumption", args.consumption)

    print("main() called")


if __name__ == "__main__":
    main()
