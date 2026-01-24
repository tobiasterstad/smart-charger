from argparse import ArgumentParser
from paho.mqtt import client as mqtt_client
import logging

logger = logging.getLogger(__name__)

client_id = 'smart-charger-client-mqtt'
port = 1883
broker = '10.100.0.10'

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
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)

    parser = ArgumentParser()
    parser.add_argument("--connect-vehicle", type=str, help="Connect to vehicle")
    parser.add_argument("--connect-charger", type=str, help="Connect charger")
    parser.add_argument("--vehicle", type=str, help="Vehicle id", default="leaf")
    parser.add_argument("--charger", type=str, help="Charger id", default="gpn018087")
    args = parser.parse_args()

    client = connect_mqtt()

    if args.connect_charger:
        value = "true" if args.connect_charger == "true" else "false"
        logger.info(f"Publishing charger connected {value}")
        client.publish(f"terstad/smartcharger/chargers/{args.charger}/connected", value)
    elif args.connect_vehicle:
        value = "true" if args.connect_vehicle == "true" else "false"
        logger.info(f"Publishing vehicle connected {value}")
        client.publish(f"terstad/vehicles/{args.vehicle}/connected", value)


    print("main() called")

if __name__ == '__main__':
    main()