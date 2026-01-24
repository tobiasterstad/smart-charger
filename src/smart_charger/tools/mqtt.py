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
    parser.add_argument("--connect-vehicle", type=str, help="Connect to vehicle, <vehicle>:true/false")
    parser.add_argument("--connect-charger", type=str, help="Connect charger")
    parser.add_argument("--update-soc", type=str, help="Update SOC for vehicle, <vehicle>:<SOC>")
    args = parser.parse_args()

    client = connect_mqtt()

    if args.connect_charger:
        charger = args.connect_charger.split(":")[0]
        value = args.connect_charger.split(":")[1]
        logger.info(f"Publishing charger connected {value}")
        client.publish(f"terstad/smartcharger/chargers/{charger}/connected", value)
    elif args.connect_vehicle:
        vehicle = args.connect_vehicle.split(":")[0]
        value = args.connect_vehicle.split(":")[1]
        logger.info(f"Publishing vehicle connected {value}")
        client.publish(f"terstad/vehicles/{vehicle}/connected", value)
    elif args.update_soc:
        vehicle = args.update_soc.split(":")[0]
        soc = args.update_soc.split(":")[1]
        client.publish(f"terstad/vehicles/{vehicle}/soc", soc)


    print("main() called")

if __name__ == '__main__':
    main()