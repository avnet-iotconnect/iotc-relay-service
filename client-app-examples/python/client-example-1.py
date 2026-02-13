# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Avnet
# Authors: Nikola Markovic <nikola.markovic@avnet.com> and Zackary Andraka <zackary.andraka@avnet.com> et al.

import time
import random
import sys

# Add location of relay client module to path
CLIENT_MODULE_PATH = "/opt/demo" 
sys.path.insert(0, CLIENT_MODULE_PATH)

from iotc_relay_client import IoTConnectRelayClient

SOCKET_PATH = "/tmp/iotconnect-relay.sock"
CLIENT_ID = "random_data_generator_2"

WEATHER = ["snowing", "raining", "cloudy", "windy", "sunny", "partly cloudy", "hailing", "hurricane"]

def handle_cloud_command(command_name, command_parameters): 
    print(f"Command received: {command_name}")
    
    if command_name == "Command_A":
        print(f"Executing protocol for Command_A with parameters: {command_parameters}")
    elif command_name == "Command_B":
        print(f"Executing protocol for Command_B with parameters: {command_parameters}")
    else:
        print(f"Command not recognized: {command_name}")


def generate_random_data():
    return random.randint(-100, -1), random.choice(WEATHER)


def main():
    # Initialize and start client (handles connection and reconnection automatically)
    client = IoTConnectRelayClient(
        socket_path=SOCKET_PATH,
        client_id=CLIENT_ID,
        command_callback=handle_cloud_command
    )
    client.start()
    
    try:
        while True:
            number_neg, weather = generate_random_data()
            print(f"Negative Number: {number_neg}, Weather: {weather}")
            
            # Send telemetry if connected
            if client.is_connected():
                client.send_telemetry({"random_number_neg": number_neg, "random_weather": weather})
            
            time.sleep(5)
    
    except KeyboardInterrupt:
        print("\nExiting gracefully...")
        client.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
