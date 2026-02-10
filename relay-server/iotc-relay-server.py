# SPDX-License-Identifier: MIT
# Copyright (C) 2024 Avnet
# Authors: Nikola Markovic <nikola.markovic@avnet.com> and Zackary Andraka <zackary.andraka@avnet.com> et al.

import sys
import time
import subprocess
import os
import urllib.request
import json
import socket
import threading
import requests
from avnet.iotconnect.sdk.lite import Client, DeviceConfig, C2dCommand, Callbacks, DeviceConfigError
from avnet.iotconnect.sdk.lite import __version__ as SDK_VERSION
from avnet.iotconnect.sdk.sdklib.mqtt import C2dAck, C2dOta

DATA_FREQUENCY = 5  # Seconds between telemetry transmissions
SOCKET_PATH = "/tmp/iotconnect-relay.sock"
TCP_PORT = 8899  # TCP port for containerized/remote clients (set to 0 to disable)
TCP_BIND_ADDRESS = "0.0.0.0"  # Bind address for TCP listener
CONFIG_PATH = "/home/weston/demo/iotcDeviceConfig.json"
CERT_PATH = "/home/weston/demo/device-cert.pem"
KEY_PATH = "/home/weston/demo/device-pkey.pem"


class IoTConnectRelayServer:

    def __init__(self, socket_path, tcp_port=0, tcp_bind_address="0.0.0.0"):
        self.socket_path = socket_path
        self.tcp_port = tcp_port
        self.tcp_bind_address = tcp_bind_address
        self.server_socket = None
        self.tcp_server_socket = None
        self.clients = {}  # Dictionary to track connected clients
        self.clients_lock = threading.Lock()
        self.telemetry_data = {}  # Store latest telemetry from each client
        self.telemetry_lock = threading.Lock()
        self.running = False

    def start(self):
        self.running = True

        # Start Unix socket listener
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        try:
            self.server_socket.bind(self.socket_path)
            self.server_socket.listen(10)
            print(f"IoTConnect Relay server listening on {self.socket_path}")

            accept_thread = threading.Thread(target=self._accept_connections, args=(self.server_socket, "unix"), daemon=True)
            accept_thread.start()

        except Exception as e:
            print(f"Failed to start Unix socket server: {e}")
            self.running = False
            return

        # Start TCP listener if configured
        if self.tcp_port > 0:
            self.tcp_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            try:
                self.tcp_server_socket.bind((self.tcp_bind_address, self.tcp_port))
                self.tcp_server_socket.listen(10)
                print(f"IoTConnect Relay server listening on TCP {self.tcp_bind_address}:{self.tcp_port}")

                tcp_accept_thread = threading.Thread(target=self._accept_connections, args=(self.tcp_server_socket, "tcp"), daemon=True)
                tcp_accept_thread.start()

            except Exception as e:
                print(f"Failed to start TCP server: {e}")
                print("Continuing with Unix socket only.")
                self.tcp_server_socket = None

    def _accept_connections(self, server_sock, label):
        while self.running:
            try:
                client_socket, addr = server_sock.accept()
                if addr:
                    print(f"Client connected via {label} from {addr}")
                else:
                    print(f"Client connected via {label}")

                # Handle client in separate thread
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket,),
                    daemon=True
                )
                client_thread.start()

            except Exception as e:
                if self.running:
                    print(f"Error accepting {label} connection: {e}")
    
    def _handle_client(self, client_socket):
        buffer = ""
        client_id = None
        
        try:
            client_socket.settimeout(60.0)
            
            # Store client connection
            with self.clients_lock:
                # Use socket object as temporary key until we get client_id
                self.clients[id(client_socket)] = client_socket
            
            while self.running:
                data = client_socket.recv(4096).decode('utf-8')
                
                if not data:
                    break
                
                buffer += data
                
                # Process complete messages (delimited by newline)
                while '\n' in buffer:
                    message_str, buffer = buffer.split('\n', 1)
                    
                    try:
                        message = json.loads(message_str)
                        response_client_id = self._process_client_message(message, client_socket)
                        if response_client_id and not client_id:
                            client_id = response_client_id
                    
                    except json.JSONDecodeError as e:
                        print(f"Invalid JSON from client: {e}")
                        response = {"status": "error", "message": "Invalid JSON"}
                        client_socket.sendall((json.dumps(response) + "\n").encode('utf-8'))
        
        except socket.timeout:
            print(f"Client timed out")
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            # Clean up client connection
            with self.clients_lock:
                socket_id = id(client_socket)
                if socket_id in self.clients:
                    del self.clients[socket_id]
                # Also remove by client_id if we have it
                if client_id and client_id in self.clients:
                    del self.clients[client_id]
            
            try:
                client_socket.close()
            except:
                pass
            
            print(f"Client disconnected: {client_id if client_id else 'unknown'}")
    
    def _process_client_message(self, message, client_socket):
        message_type = message.get("type")
        
        if message_type == "telemetry":
            # Store telemetry data from client
            telemetry_data = message.get("data", {})
            client_id = message.get("client_id", "unknown")
            
            with self.telemetry_lock:
                self.telemetry_data[client_id] = {
                    "data": telemetry_data,
                }
            
            # Send acknowledgment
            response = {"status": "ok", "message": "Telemetry received"}
            client_socket.sendall((json.dumps(response) + "\n").encode('utf-8'))
        
        elif message_type == "register":
            # Client registration with client ID
            client_id = message.get("client_id", "unknown")
            print(f"Client registered as: {client_id}")
            
            # Update clients dictionary with proper client_id key
            with self.clients_lock:
                self.clients[client_id] = client_socket
            
            response = {"status": "ok", "message": "Registered successfully", "client_id": client_id}
            client_socket.sendall((json.dumps(response) + "\n").encode('utf-8'))
            
            return client_id
        
        else:
            # Unknown message type
            response = {"status": "error", "message": "Unknown message type"}
            client_socket.sendall((json.dumps(response) + "\n").encode('utf-8'))
        
        return None
    
    def broadcast_command(self, command_name, parameters):
        message = {
            "type": "command",
            "command_name": command_name,
            "parameters": parameters
        }
        message_str = json.dumps(message) + "\n"
        
        with self.clients_lock:
            disconnected_clients = []
            
            for client_id, client_socket in self.clients.items():
                try:
                    client_socket.sendall(message_str.encode('utf-8'))
                    print(f"Sent command to client: {client_id}")
                except Exception as e:
                    print(f"Failed to send command to {client_id}: {e}")
                    disconnected_clients.append(client_id)
            
            # Remove disconnected clients
            for client_id in disconnected_clients:
                del self.clients[client_id]
    
    def get_combined_telemetry(self):
        with self.telemetry_lock:
            if not self.telemetry_data:
                return None
            
            # If only one client, return its data directly
            if len(self.telemetry_data) == 1:
                client_data = list(self.telemetry_data.values())[0]
                return client_data["data"]
            
            # If multiple clients, collect all of their data
            combined = {}
            for client_id, client_info in self.telemetry_data.items():
                data = client_info["data"]
                for key, value in data.items():
                    # Prefix keys with client ID to avoid collisions
                    combined[key] = value
            
            return combined
    
    def get_client_count(self):
        with self.clients_lock:
            return len(self.clients)
    
    def stop(self):
        self.running = False

        # Close all client connections
        with self.clients_lock:
            for client_socket in self.clients.values():
                try:
                    client_socket.close()
                except:
                    pass
            self.clients.clear()

        # Close server sockets
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

        if self.tcp_server_socket:
            try:
                self.tcp_server_socket.close()
            except:
                pass

        # Remove Unix socket file
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except:
                pass


def extract_and_run_tar_gz(targz_filename):
    try:
        # Extract the tar.gz archive
        subprocess.run(("tar", "-xzvf", targz_filename, "--overwrite"), check=True)
        
        current_directory = os.getcwd()
        script_file_path = os.path.join(current_directory, "install.sh")
        
        # If install.sh is found, execute it then delete it
        if os.path.isfile(script_file_path):
            try:
                subprocess.run(['bash', script_file_path], check=True)
                os.remove(script_file_path)
                print(f"Successfully executed install.sh")
                return True
            except subprocess.CalledProcessError as e:
                os.remove(script_file_path)
                print(f"Error executing install.sh: {e}")
                return False
            except Exception as e:
                os.remove(script_file_path)
                print(f"An error occurred: {e}")
                return False
        else:
            print("install.sh not found in the current directory.")
            return True
            
    except subprocess.CalledProcessError:
        return False


def on_command(msg: C2dCommand):
    global c, server
    print("Received command", msg.command_name, msg.command_args, msg.ack_id)
    
    # Special handling for file-download command
    if msg.command_name == "file-download":
        if len(msg.command_args) == 1:
            status_message = "Downloading %s to device" % (msg.command_args[0])
            response = requests.get(msg.command_args[0])
            
            # Check if the request was successful (status code 200)
            if response.status_code == 200:
                # Open the file in binary write mode and save the content
                with open('package.tar.gz', 'wb') as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        file.write(chunk)
                print(f"File downloaded successfully and saved to package.tar.gz")
            else:
                print(f"Failed to download the file. Status code: {response.status_code}")
            
            c.send_command_ack(msg, C2dAck.CMD_SUCCESS_WITH_ACK, status_message)
            print(status_message)
            
            # Extract and install the package
            extraction_success = extract_and_run_tar_gz('package.tar.gz')
            
            print("Download command successful. Will restart the application...")
            print("")
            sys.stdout.flush()
            
            # Restart the process to apply updates
            os.execv(sys.executable, [sys.executable, __file__] + [sys.argv[0]])
        else:
            c.send_command_ack(msg, C2dAck.CMD_FAILED, "Expected 1 argument")
            print("Expected 1 command argument, but got", len(msg.command_args))
    
    # Broadcast all other commands to all connected clients via socket
    else:
        params = " ".join(msg.command_args)
        client_count = server.get_client_count()
        print(f"Broadcasting command --- {msg.command_name} {params} --- to {client_count} client(s) via IoTConnect Relay.")
        
        # Broadcast command to all clients
        server.broadcast_command(msg.command_name, params)
        
        # Send acknowledgement if required by device template
        if msg.ack_id is not None:
            c.send_command_ack(msg, C2dAck.CMD_SUCCESS_WITH_ACK, f"Command broadcast to {client_count} client(s)")


def on_ota(msg: C2dOta):
    global c
    print("Starting OTA downloads for version %s" % msg.version)
    c.send_ota_ack(msg, C2dAck.OTA_DOWNLOADING)
    
    extraction_success = False
    
    # Download all files in the OTA package
    for url in msg.urls:
        print("Downloading OTA file %s from %s" % (url.file_name, url.url))
        try:
            urllib.request.urlretrieve(url.url, url.file_name)
        except Exception as e:
            print("Encountered download error", e)
            error_msg = "Download error for %s" % url.file_name
            break
        
        # Process .tar.gz files
        if url.file_name.endswith(".tar.gz"):
            extraction_success = extract_and_run_tar_gz(url.file_name)
            if extraction_success is False:
                break
        else:
            print("ERROR: Unhandled file format for file %s" % url.file_name)
    
    # Restart application if OTA was successful
    if extraction_success is True:
        print("OTA successful. Will restart the application...")
        c.send_ota_ack(msg, C2dAck.OTA_DOWNLOAD_DONE)
        print("")
        sys.stdout.flush()
        
        # Restart the process to apply updates
        os.execv(sys.executable, [sys.executable, __file__] + [sys.argv[0]])
    else:
        print('Encountered a download processing error. Not restarting.')


def on_disconnect(reason: str, disconnected_from_server: bool):
    """Handle disconnection events from IOTCONNECT"""
    print("Disconnected%s. Reason: %s" % (" from server" if disconnected_from_server else "", reason))


# Main

c = None
server = None

try:
    # Start the relay server (Unix socket + optional TCP listener)
    server = IoTConnectRelayServer(SOCKET_PATH, tcp_port=TCP_PORT, tcp_bind_address=TCP_BIND_ADDRESS)
    server.start()
    
    # Give the server a moment to initialize
    time.sleep(1)
    
    # Load device configuration from files
    device_config = DeviceConfig.from_iotc_device_config_json_file(
        device_config_json_path=CONFIG_PATH,
        device_cert_path=CERT_PATH,
        device_pkey_path=KEY_PATH
    )

    # Initialize IOTCONNECT client with callbacks
    c = Client(
        config=device_config,
        callbacks=Callbacks(
            ota_cb=on_ota,
            command_cb=on_command,
            disconnected_cb=on_disconnect
        )
    )
    
    # Main telemetry loop
    while True:
        # Ensure connection is established
        if not c.is_connected():
            print('(re)connecting...')
            c.connect()
            if not c.is_connected():
                # Still unable to connect after retries
                print('Unable to connect. Exiting.')
                sys.exit(2)

        # Get combined telemetry from all connected clients and transmit to IOTCONNECT
        telemetry = server.get_combined_telemetry()
        if telemetry:
            c.send_telemetry(telemetry)
        
            # Clear telemetry data after sending to prevent re-sending stale data
            with server.telemetry_lock:
                server.telemetry_data.clear()
    
        # If no clients connected
        if server.get_client_count() == 0:
            print("No clients connected to IoTConnect Relay")
    
        # Wait before next transmission
        time.sleep(DATA_FREQUENCY)
        
except DeviceConfigError as dce:
    # Handle device configuration errors (invalid config files, missing certs, etc.)
    print(dce)
    sys.exit(1)

except KeyboardInterrupt:
    # Handle graceful shutdown on Ctrl+C
    print("Exiting.")
    if c and c.is_connected():
        c.disconnect()
    if server:
        server.stop()
    sys.exit(0)

except Exception as e:
    print(f"Unexpected error: {e}")
    if server:
        server.stop()
    sys.exit(1)
