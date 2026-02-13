# /IOTCONNECT Relay Service Guide

1. [Introduction](#1-introduction)
2. [Device Setup](#2-device-setup)
3. [Download the /IOTCONNECT Relay Server and Client Code](#3-download-the-iotconnect-relay-server-and-client-code)
4. [Modifications to User Applications](#4-modifications-to-user-applications)
5. [Update Device Template](#5-update-device-template)
6. [Set Up the /IOTCONNECT Relay Service to Run On Boot](#6-set-up-the-iotconnect-relay-service-to-run-on-boot)
7. [Using the /IOTCONNECT Relay Service with User Applications](#7-using-the-iotconnect-relay-service-with-user-applications)
8. [Resources](#8-resources)

# 1. Introduction

This guide will walk you through how to enable the /IOTCONNECT Relay Service on a supported device
to transmit and receive data to/from any Python or C process via Unix socket or TCP. This allows any user
to report data from their existing applications to /IOTCONNECT and receive cloud commands from /IOTCONNECT
while making minimal modifications.

The relay server listens on both a Unix domain socket and a TCP port (default 8899), so applications
running inside containers can connect directly via TCP without needing external bridging tools like socat.

This guide also includes working example Python and C applications (to resemble user applications) and detailed 
instructions on the necessary modifications for connecting it to the /IOTCONNECT service to enable telemetry reporting 
and cloud-command handling.

After following this guide you should be able to connect your own custom application to /IOTCONNECT with ease!

# 2. Device Setup

In the Quickstart guide for your supported board in the [/IOTCONNECT Python Lite Demos repo](https://github.com/avnet-iotconnect/iotc-python-lite-sdk-demos/tree/main), 
follow each of the steps until you reach the "Using the Demo" step. 

This will walk users through how to set up hardware, configure the software, and onboard a device into /IOTCONNECT.

> [!NOTE]
>  Since these steps can differ board-to-board it is important to look at the Quickstart **for your specific device.**

# 3. Download the /IOTCONNECT Relay Server and Client Code

First download the /IOTCONNECT Relay Server application using these commands in the console:

```
wget -O /opt/demo/iotc-relay-server.py https://raw.githubusercontent.com/avnet-iotconnect/iotc-relay-service/main/relay-server/iotc-relay-server.py
```

> [!NOTE]
> This same Python server script will be used regardless of whether the customer application is Python-based or not. Using 
> Unix sockets allows it to communicate with both Python and C programs.

Next, download the appropriate client module code for your application(s).

## Python Applications

For Python applications, download the Python client module using this console command: 

> [!NOTE]
> You can download the module to a different directory but **ensure that you update the locations in all
> other references to it.**

```
wget -O /opt/demo/iotc_relay_client.py https://raw.githubusercontent.com/avnet-iotconnect/iotc-relay-service/main/client-module/python/iotc_relay_client.py
```

## C Applications

For C applications, download the C client module, header file, and Makefile using these commands:

> [!IMPORTANT]
> In each command, users should replace `<USER APPLICATION DIRECTORY>` with the local directory where the custom user 
> application is stored. This makes compilation less complex.

```
wget -O <USER APPLICATION DIRECTORY>/iotc_relay_client.c https://raw.githubusercontent.com/avnet-iotconnect/iotc-relay-service/main/client-module/c/iotc_relay_client.c
```
```
wget -O <USER APPLICATION DIRECTORY>/iotc_relay_client.h https://raw.githubusercontent.com/avnet-iotconnect/iotc-relay-service/main/client-module/c/iotc_relay_client.h
```

# 4. Modifications to User Applications

> [!NOTE]
> For your convenience, if you just wish to test out the Relay functionality you can download 1 or more ready-to-use
> example custom client applications with these commands:
> 
> Python application that generates random positive integers and selects random color strings:
> ```
> wget https://raw.githubusercontent.com/avnet-iotconnect/iotc-relay-service/refs/heads/main/client-app-examples/python/client-example-0.py
> ```
> 
> Python application that generates random negative integers and selects random weather strings:
> ```
> wget https://raw.githubusercontent.com/avnet-iotconnect/iotc-relay-service/refs/heads/main/client-app-examples/python/client-example-1.py
> ```
> 
> C application that generates random positive decimal numbers between 0 and 1 and selects random animal strings:
> ```
> wget https://raw.githubusercontent.com/avnet-iotconnect/iotc-relay-service/refs/heads/main/client-app-examples/c/client-example-2.c
> ```
> 
> C application that generates random negative decimal numbers between -1 and 0 and selects random name strings:
> ```
> wget https://raw.githubusercontent.com/avnet-iotconnect/iotc-relay-service/refs/heads/main/client-app-examples/c/client-example-3.c
> ```
> 
> Step 4 walks you through how to create an application like these yourself, so if you downloaded it you can skip to [Step 5](#5-update-device-template).

## Python Applications

Here is a basic Python script that can represent an existing user application:

```python
import time
import random
import sys

COLORS = ["red", "blue", "green", "yellow", "orange", "purple", "black", "white"]


def generate_random_data():
    random_int = random.randint(0, 100)
    random_color = random.choice(COLORS)
    return random_int, random_color


def main():
    try:
        while True:
            number, color = generate_random_data()
            print(f"Number: {number}, Color: {color}")
            time.sleep(5)

    except KeyboardInterrupt:
        print("Exiting...")
        sys.exit(0)


if __name__ == "__main__":
    main()
```

The first addition users need to make is importing the iotc_relay_client
module (from the location it was downloaded to), and then adding basic connection config:

```python
# Add location of relay client module to path
CLIENT_MODULE_PATH = "/opt/demo"
sys.path.insert(0, CLIENT_MODULE_PATH)

from iotc_relay_client import IoTConnectRelayClient

SOCKET_PATH = "/tmp/iotconnect-relay.sock"
CLIENT_ID = "random_data_generator"
```

> [!TIP]
> If your application runs inside a container (e.g., Docker, Arduino App Lab) and cannot access
> the host's Unix socket, use a TCP connection instead:
> ```python
> SOCKET_PATH = "tcp://172.17.0.1:8899"
> ```
> Replace the IP and port with the appropriate values for your environment. The default TCP port
> for the relay server is `8899`.

The next addition is going to be a handler function for acting upon the received cloud commands from the server. A basic 
version of this could be:

```python
def handle_cloud_command(command_name, command_parameters): 
    print(f"Command received: {command_name}")
    
    if command_name == "Command_A":
        print(f"Executing protocol for Command_A with parameters: {command_parameters}")
    elif command_name == "Command_B":
        print(f"Executing protocol for Command_B with parameters: {command_parameters}")
    else:
        print(f"Command not recognized: {command_name}")

```
> [!TIP]
> The cloud command handler should always expect to receive a string "command_name" (basic command name called) and a string
> "command_parameters" (space-separated parameters).

The final modifications are going to be in the main loop of the application to initialize connection and then utilize the 
socket:

```python
def main():
    # Initialize and start client
    client = IoTConnectRelayClient(
        socket_path=SOCKET_PATH,
        client_id=CLIENT_ID,
        command_callback=handle_cloud_command
    )
    client.start()
    
    try:
        while True:
            number, color = generate_random_data()
            print(f"Number: {number}, Color: {color}")
            
            # Send telemetry if connected
            if client.is_connected():
                client.send_telemetry({"random_number": number, "random_color": color})
            
            time.sleep(5)
    
    except KeyboardInterrupt:
        print("\nExiting gracefully...")
        client.stop()
        sys.exit(0)
```

Altogether, the /IOTCONNECT Relay-compatible version of the example script would be:

```python
import time
import random
import sys

# Add location of relay client module to path
CLIENT_MODULE_PATH = "/opt/demo" 
sys.path.insert(0, CLIENT_MODULE_PATH)

from iotc_relay_client import IoTConnectRelayClient

SOCKET_PATH = "/tmp/iotconnect-relay.sock"
CLIENT_ID = "random_data_generator"

COLORS = ["red", "blue", "green", "yellow", "orange", "purple", "black", "white"]

def handle_cloud_command(command_name, command_parameters): 
    print(f"Command received: {command_name}")
    
    if command_name == "Command_A":
        print(f"Executing protocol for Command_A with parameters: {command_parameters}")
    elif command_name == "Command_B":
        print(f"Executing protocol for Command_B with parameters: {command_parameters}")
    else:
        print(f"Command not recognized: {command_name}")


def generate_random_data():
    return random.randint(0, 100), random.choice(COLORS)


def main():
    # Initialize and start client
    client = IoTConnectRelayClient(
        socket_path=SOCKET_PATH,
        client_id=CLIENT_ID,
        command_callback=handle_cloud_command
    )
    client.start()
    
    try:
        while True:
            number, color = generate_random_data()
            print(f"Number: {number}, Color: {color}")
            
            # Send telemetry if connected
            if client.is_connected():
                client.send_telemetry({"random_number": number, "random_color": color})
            
            time.sleep(5)
    
    except KeyboardInterrupt:
        print("\nExiting gracefully...")
        client.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
```

> [!IMPORTANT]
> If you are using multiple clients on your device to report data to the server, **ensure that they do not use the same 
> telemetry data variable names as each other.** Some of the data could be overwritten and lost.

## C Applications

Here is a basic C program that can represent an existing user application:
```c
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>

static const char *ANIMALS[] = {
    "dog", "cat", "bear", "fish", 
    "bird", "snake", "turtle", "rabbit"
};
#define NUM_ANIMALS (sizeof(ANIMALS) / sizeof(ANIMALS[0]))

static void generate_random_data(float *number_decimal, const char **animal)
{
    *number_decimal = (float)(rand() % 101) / 100.0f;
    *animal = ANIMALS[rand() % NUM_ANIMALS];
}

int main(void)
{
    float number_decimal;
    const char *animal;
    
    srand(time(NULL));
    
    while (1) {
        generate_random_data(&number_decimal, &animal);
        printf("Number: %.2f, Animal: %s\n", number_decimal, animal);
        sleep(5);
    }
    
    return 0;
}
```

The first addition users need to make is including the relay client header and adding basic configuration:
```c
#include "iotc_relay_client.h"

#define SOCKET_PATH "/tmp/iotconnect-relay.sock"
#define CLIENT_ID "c_data_generator"
```

> [!TIP]
> For containerized environments, use a TCP connection instead:
> ```c
> #define SOCKET_PATH "tcp://172.17.0.1:8899"
> ```

The next addition is a handler function for acting upon received cloud commands from the server. A basic version of this 
could be:
```c
static void handle_cloud_command(
    const char *command_name,
    const char *command_parameters,
    void *user_data)
{
    (void)user_data;
    
    printf("Command received: %s\n", command_name);
    
    if (strcmp(command_name, "Command_A") == 0) {
        printf("Executing protocol for Command_A with parameters: %s\n", 
               command_parameters);
    } else if (strcmp(command_name, "Command_B") == 0) {
        printf("Executing protocol for Command_B with parameters: %s\n", 
               command_parameters);
    } else {
        printf("Command not recognized: %s\n", command_name);
    }
}
```

> [!TIP]
> The cloud command handler receives three parameters: `command_name` (command name string), `command_parameters` 
> (space-separated parameters string), and `user_data` (optional user context pointer which can be NULL).

The final modifications are in the main function to add signal handling, initialize the client connection, and send telemetry:
```c
static IotcRelayClient *g_client = NULL;

static void signal_handler(int signum)
{
    (void)signum;
    printf("\nExiting gracefully...\n");
    if (g_client) {
        iotc_relay_client_stop(g_client);
        iotc_relay_client_destroy(g_client);
    }
    exit(0);
}

int main(void)
{
    int ret;
    float number_decimal;
    const char *animal;
    char json_buffer[256];
    
    srand(time(NULL));
    signal(SIGINT, signal_handler);
    
    /* Initialize and start client */
    g_client = iotc_relay_client_create(
        SOCKET_PATH,
        CLIENT_ID,
        handle_cloud_command,
        NULL
    );
    
    if (!g_client) {
        fprintf(stderr, "Failed to create client\n");
        return 1;
    }
    
    iotc_relay_client_start(g_client);
    
    while (1) {
        generate_random_data(&number_decimal, &animal);
        printf("Number: %.2f, Animal: %s\n", number_decimal, animal);
        
        /* Send telemetry if connected */
        if (iotc_relay_client_is_connected(g_client)) {
            snprintf(json_buffer, sizeof(json_buffer),
                     "{\"random_number_decimal\":%.2f,\"random_animal\":\"%s\"}",
                     number_decimal, animal);
            
            iotc_relay_client_send_telemetry(g_client, json_buffer);
        }
        
        sleep(5);
    }
    
    return 0;
}
```

Altogether, the /IOTCONNECT Relay-compatible version of the example program would be:
```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>
#include "iotc_relay_client.h"

#define SOCKET_PATH "/tmp/iotconnect-relay.sock"
#define CLIENT_ID "c_data_generator"

static const char *ANIMALS[] = {
    "dog", "cat", "bear", "fish", 
    "bird", "snake", "turtle", "rabbit"
};
#define NUM_ANIMALS (sizeof(ANIMALS) / sizeof(ANIMALS[0]))

static IotcRelayClient *g_client = NULL;

static void signal_handler(int signum)
{
    (void)signum;
    printf("\nExiting gracefully...\n");
    if (g_client) {
        iotc_relay_client_stop(g_client);
        iotc_relay_client_destroy(g_client);
    }
    exit(0);
}

static void handle_cloud_command(
    const char *command_name,
    const char *command_parameters,
    void *user_data)
{
    (void)user_data;
    
    printf("Command received: %s\n", command_name);
    
    if (strcmp(command_name, "Command_A") == 0) {
        printf("Executing protocol for Command_A with parameters: %s\n", 
               command_parameters);
    } else if (strcmp(command_name, "Command_B") == 0) {
        printf("Executing protocol for Command_B with parameters: %s\n", 
               command_parameters);
    } else {
        printf("Command not recognized: %s\n", command_name);
    }
}

static void generate_random_data(float *number_decimal, const char **animal)
{
    *number_decimal = (float)(rand() % 101) / 100.0f;
    *animal = ANIMALS[rand() % NUM_ANIMALS];
}

int main(void)
{
    int ret;
    float number_decimal;
    const char *animal;
    char json_buffer[256];
    
    srand(time(NULL));
    signal(SIGINT, signal_handler);
    
    g_client = iotc_relay_client_create(
        SOCKET_PATH,
        CLIENT_ID,
        handle_cloud_command,
        NULL
    );
    
    if (!g_client) {
        fprintf(stderr, "Failed to create client\n");
        return 1;
    }
    
    iotc_relay_client_start(g_client);
    
    while (1) {
        generate_random_data(&number_decimal, &animal);
        printf("Number: %.2f, Animal: %s\n", number_decimal, animal);
        
        if (iotc_relay_client_is_connected(g_client)) {
            snprintf(json_buffer, sizeof(json_buffer),
                     "{\"random_number_decimal\":%.2f,\"random_animal\":\"%s\"}",
                     number_decimal, animal);
            
            iotc_relay_client_send_telemetry(g_client, json_buffer);
        }
        
        sleep(5);
    }
    
    return 0;
}
```

> [!IMPORTANT]
> Telemetry data must be formatted as a JSON string. Use `snprintf()` to create properly formatted JSON with your data 
> values before calling `iotc_relay_client_send_telemetry()`.

> [!IMPORTANT]
> If you are using multiple clients on your device to report data to the server, **ensure that they do not use the same 
> telemetry data variable names as each other.** Some of the data could be overwritten and lost.

After creating your modified C application(s), modify your Makefile(s) or compilation command(s) to include the `iotc_relay_client.c` 
module, and then recompile.

# 5. Update Device Template

For /IOTCONNECT to recognize the data attributes you report and send commands to your device, the template for your device 
will need to be updated.

To create a new template, log into your /IOTCONNECT account at https://console.iotconnect.io/login and then in the blue 
vertical toolbar on the left side of the page, hover over the processor icon and then click "Device" in the resulting dropdown.

<img src="./media/device-page.png" alt="">

Now in the Devices page, in the blue horizontal toolbar at the bottom of the screen click on the "Templates" button.

<img src="./media/templates-button.png" alt="">

In the Templates page, click on the blue "Create Template" button in the top-right corner.

<img src="./media/create-template-button.png" alt="">

Fill in the Template Code and Template Name fields with your desired alphanumeric values (must start with a letter), and 
leave the Authentication Type and Device Message Version on their default values. Then click "Save".

> [!TIP]
> For simplicity we recommend making the Template Code and Template Name the same values.

In the resulting page, you can add your data attributes, cloud commands, and adjust your data frequency.

If your Data Frequency is not set to 5 by default, it is recommended to change it to 5 since that is the frequency that 
the Relay application expects by default.

> [!NOTE]
> If the /IOTCONNECT UI says you cannot set the Data Frequency as low as you would like, submit a support ticket (bottom 
> of the vertical toolbar on the left edge of the page) requesting the value be changed to 5 for that template.

To add Attributes (data fields) to your template, click on the "Attributes" tab.

<img src="./media/attributes-tab.png" alt="">

Populate the "Local Name" with the exact key name you used for that data field to send it to the Relay server. For the 
first Python example script from above, the Local Names for the 2 attributes would be `random_color` and `random_number`.

> [!NOTE]
> If using multiple clients, add the attributes for all data fields being sent. Remember that re-using the same attribute 
> names across multiple clients is not recommended because the server will only relay the latest value for each attribute 
> during each telemetry report. Re-using names will result in lost data due to over-writing.

Use the "Data Type" dropdown and select the type that matches the data being reported. For the first Python example 
script from above, the Data Type for `random_color` would be STRING and the Data Type for `random_number` would be INTEGER.

> [!TIP]
> For any non-whole number data (not including GPS coordinates, use LATLONG for those), it is recommended that the 
> DECIMAL data type be used.

If you are reporting data objects, you can use the OBJECT data type and then add member-attributes of specific types 
within that object. 

> [!IMPORTANT]
> Ensure that the Local Names are **identical** to the key names used for sending the data to the Relay server, as no 
> modifications to the data are made by the Relay server.

After an attribute is configured, click the "Save" button to add it to the template.

To add Cloud Commands, click on the "Commands" tab.

<img src="./media/commands-tab.png" alt="">

Fill in the "Command Name" and "Command" fields with the values your command handler 
expects to receive for the "command_name" key.

> [!NOTE]
> For simplicity, populate the "Command Name" and "Command" fields with the same values.

If the nature of your command would require a parameter, toggle the "Parameter Required" 
switch to the "ON" position. This will prevent a user from accidentally sending a command 
without a necessary parameter.

Toggle the "Receipt Required" switch to the "ON" position for all commands you add, since 
the /IOTCONNECT Relay application is programmed to send an acknowledgement back to cloud 
whenever a command is received.

For the example script from above, you would enter `Command_A` for both fields for the first 
command and then `Command_B` for both fields for the second command. The "Parameter Required" 
switch can be left OFF but the "Receipt Required" should be turned ON.

After a command is configured, click the "Save" button to add it to the template.

Once all desired attributes and commands have been added, navigate back to the "Device" page 
of /IOTCONNECT and then click on your specific device name to be taken to your device's page.

In your device's page, click on the pen-and-paper icon next to the "Template" selection.

<img src="./media/edit-template.png" alt="">

In the resulting drop-down, select the name of the new template you just created and that new 
template will instantly be assigned to your device.

# 6. Set Up the /IOTCONNECT Relay Service to Run on Boot

To have the iotc-relay-server.py run on boot in the background as a service, first users need to 
create a service file called `iotconnect-relay.service` in the directory `/etc/systemd/system/`.

Here is an example service file that will work on Linux devices with
`iotc-relay-server.py` in the `/opt/demo` directory:

> [!NOTE]
> Directly download this service file to the correct directory of your device by executing this command:
> ```
> sudo wget -O /etc/systemd/system/iotconnect-relay.service https://raw.githubusercontent.com/avnet-iotconnect/iotc-relay-service/main/service-file/iotconnect-relay.service
> ```

```
[Unit]
Description=IoTConnect Relay Server
After=network.target

[Service]
Type=simple
User=<your-user>
WorkingDirectory=/opt/demo
ExecStart=/usr/bin/python3 /opt/demo/iotc-relay-server.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Environment variables (if needed)
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
```
> [!IMPORTANT]
> Make sure to replace `<your-user>` in the `User` field with a valid non-root user on your device,
> and to modify the working directory and exec start fields to the directory where iotc-relay-server.py
> is located on your device.
>
> It is recommended to **not** use `root` as the user for the service to avoid permissions errors
> in the socket system when running a client as a non-root user.
>
> If your device does not already have a non-root user, you can create one with the following commands:
> ```
> sudo useradd -m -s /bin/bash iotc
> sudo usermod -aG sudo iotc
> ```
> This creates a user called `iotc` with a home directory and adds it to the `sudo` group.
> You can replace `iotc` with any username you prefer.
>
> You will need to give your user ownership of the /IOTCONNECT config file and certificates if you
> were logged in as `root` during the initial QuickStart. Do so with this command (modify `<user>` and `<group>`):
> ```
> sudo chown <user>:<group> /opt/demo/device-cert.pem /opt/demo/device-pkey.pem /opt/demo/iotcDeviceConfig.json
> ```
> For example on a device that uses an `iotc` user in the `iotc` group, use this command:
> ```
> sudo chown iotc:iotc /opt/demo/device-cert.pem /opt/demo/device-pkey.pem /opt/demo/iotcDeviceConfig.json
> ```

After the service file has been written, execute these commands to enable and start the service:

```
sudo systemctl daemon-reload
sudo systemctl enable iotconnect-relay.service
sudo systemctl start iotconnect-relay.service
```

> [!TIP]
> Here are some console commands that can be useful for managing, debugging, and monitoring the /IOTCONNECT
> Relay Service:
> 
> Check if the service is running
> ```
> sudo systemctl status iotconnect-relay.service
> ```
>
> View live logs
> ```
> sudo journalctl -u iotconnect-relay.service -f
> ```
>
> View recent logs
> ```
> sudo journalctl -u iotconnect-relay.service -n 50
> ```
> 
> Stop the service
> ```
> sudo systemctl stop iotconnect-relay.service
> ```
>
> Restart the service
> ```
> sudo systemctl restart iotconnect-relay.service
> ```
>
> Disable auto-start on boot
> ```
> sudo systemctl disable iotconnect-relay.service
> ```
> 
> View all logs
> ```
> sudo journalctl -u iotconnect-relay.service
> ```
>
> Clear old logs
> ```
> sudo journalctl --vacuum-time=7d
> ```


# 7. Using the /IOTCONNECT Relay Service with User Applications

After the Relay Service has been enabled and started, all that users need to do is run their 
(modified) application(s) as they normally would. Data from the application(s) will be sent to the server 
and transmitted to /IOTCONNECT at the data frequency specified in `iotc-relay-server.py`.

> [!NOTE]
> If a user needs to change the data frequency of the server, they can do so by modifying the `DATA_FREQUENCY` value in
> `iotc-relay-server.py`. If the desired data frequency is lower than the value in the /IOTCONNECT device template, the value in the
> template must first be lowered. *If the template-editing page shows an alert saying that the desired data frequency is too low, please
> submit a [support ticket](https://docs.iotconnect.io/iotconnect/user-manuals/support-tickets/) in /IOTCONNECT asking
> for the data frequency of your template to be changed.*

> [!TIP]
> The relay server also listens on TCP port `8899` by default, which allows clients running inside
> containers to connect without needing external bridging tools. To change the TCP port, modify the
> `TCP_PORT` value in `iotc-relay-server.py`. Set `TCP_PORT = 0` to disable the TCP listener entirely.

Commands sent from /IOTCONNECT will be transmitted from the server to the client app(s) to be handled 
by the newly-added `handle_cloud_command` function.

Users can conveniently view live telemetry data ("Live Data" tab) and send device commands ("Command" tab) from their device's page in 
the /IOTCONNECT online UI.

# 8. Resources
* To see the setup and onboarding guide for specific boards check out [the /IOTCONNECT Python Lite SDK Demos repo](https://github.com/avnet-iotconnect/iotc-python-lite-sdk-demos/tree/main)
* [/IOTCONNECT Python Lite SDK](https://github.com/avnet-iotconnect/iotc-python-lite-sdk)
* [/IOTCONNECT Overview](https://www.iotconnect.io/)
* [/IOTCONNECT Knowledgebase](https://help.iotconnect.io/)
