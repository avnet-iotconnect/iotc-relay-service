# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Avnet
# Authors: Nikola Markovic <nikola.markovic@avnet.com> and Zackary Andraka <zackary.andraka@avnet.com> et al.

import time
import socket
import json
import threading


class IoTConnectRelayClient:
    """Relay client for the Avnet IoTConnect Relay Service.

    If socket_path starts with "tcp://", connects via TCP instead of a Unix socket.
    Example: socket_path = "tcp://172.17.0.1:8899"

    This is useful when the app runs in a container and cannot access
    the host's Unix socket at /tmp/iotconnect-relay.sock directly.
    """

    def __init__(self, socket_path, client_id, command_callback=None, reconnect_delay=5):
        self.socket_path = socket_path
        self.client_id = client_id
        self.command_callback = command_callback
        self.reconnect_delay = reconnect_delay
        self.socket = None
        self.connected = False
        self.lock = threading.Lock()
        self.receive_thread = None
        self.reconnect_thread = None
        self.running = False
        
    def start(self):
        self.running = True
        
        # Try initial connection
        if self.connect():
            print("Initial connection successful!")
        else:
            print("Initial connection failed. Will continue to retry in background...")
        
        # Start background reconnection thread
        self.reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self.reconnect_thread.start()
    
    def stop(self):
        print("Stopping client...")
        self.running = False
        self.disconnect()
        
        # Wait for reconnect thread to finish
        if self.reconnect_thread:
            self.reconnect_thread.join(timeout=self.reconnect_delay + 1)
    
    def _reconnect_loop(self):
        while self.running:
            if not self.connected:
                if self.connect():
                    print("Reconnection successful!")
            time.sleep(self.reconnect_delay)

    def _parse_tcp_target(self):
        """Parse a tcp://host:port target string. Returns (host, port) or None."""
        if not isinstance(self.socket_path, str) or not self.socket_path.startswith("tcp://"):
            return None

        target = self.socket_path[len("tcp://"):]
        # Allow IPv6 in brackets: tcp://[::1]:8899
        if target.startswith("[") and "]" in target:
            host = target[1:target.index("]")]
            rest = target[target.index("]") + 1:]
            if not rest.startswith(":"):
                raise ValueError(f"Invalid tcp target: {self.socket_path}")
            port = int(rest[1:])
            return (host, port)

        if ":" not in target:
            raise ValueError(f"Invalid tcp target (missing :port): {self.socket_path}")
        host, port_str = target.rsplit(":", 1)
        return (host, int(port_str))

    def connect(self):
        try:
            tcp_target = self._parse_tcp_target()

            if tcp_target is not None:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(5.0)
                self.socket.connect(tcp_target)
                print(f"Connected to IoTConnect Relay server via TCP at {tcp_target[0]}:{tcp_target[1]}")
            else:
                self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.socket.settimeout(5.0)
                self.socket.connect(self.socket_path)
                print(f"Connected to IoTConnect Relay server at {self.socket_path}")

            self.connected = True
            
            # Register with the server
            self._send_message({
                "type": "register",
                "client_id": self.client_id
            })
            
            # Start receiving thread for commands
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
    
            return True
            
        except Exception as e:
            self.connected = False
            self.socket = None
            return False
    
    def disconnect(self):
        self.connected = False
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
    
    def _send_message(self, message):
        try:
            message_str = json.dumps(message) + "\n"
            self.socket.sendall(message_str.encode('utf-8'))
            return True
        except Exception as e:
            print(f"Error sending message: {e}")
            self.connected = False
            return False
    
    def send_telemetry(self, data):
        with self.lock:
            if not self.connected:
                return False
            
            message = {
                "type": "telemetry",
                "client_id": self.client_id,
                "data": data
            }
            
            return self._send_message(message)
    
    def _receive_loop(self):
        buffer = ""
        
        try:
            while self.running and self.connected:
                try:
                    data = self.socket.recv(4096).decode('utf-8')
                    
                    if not data:
                        print("Server closed connection")
                        self.connected = False
                        break
                    
                    buffer += data
                    
                    # Process complete messages (delimited by newline)
                    while '\n' in buffer:
                        message_str, buffer = buffer.split('\n', 1)
                        
                        try:
                            message = json.loads(message_str)
                            self._handle_server_message(message)
                        except json.JSONDecodeError as e:
                            print(f"Invalid JSON from server: {e}")
                
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"Error in receive loop: {e}")
                    self.connected = False
                    break
        
        finally:
            self.connected = False
    
    def _handle_server_message(self, message):
        message_type = message.get("type")
        
        if message_type == "command":
            # Handle command from IoTConnect cloud
            command_name = message.get("command_name")
            parameters = message.get("parameters", "")
            
            # Call the user-provided callback if it exists
            if self.command_callback:
                try:
                    self.command_callback(command_name, parameters)
                except Exception as e:
                    print(f"Error in command callback: {e}")
        
        elif message_type == "response" or message.get("status"):
            # Acknowledgment from server
            pass
        
        else:
            print(f"Unknown message type from server: {message_type}")
    
    def is_connected(self):
        return self.connected
