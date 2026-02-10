/*
 * SPDX-License-Identifier: MIT
 * Copyright (C) 2026 Avnet
 * Authors: Nikola Markovic <nikola.markovic@avnet.com> and Zackary Andraka <zackary.andraka@avnet.com> et al.
 */

#ifndef IOTC_RELAY_CLIENT_H
#define IOTC_RELAY_CLIENT_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>
#include <stddef.h>

/* Maximum sizes for buffers */
#define IOTC_RELAY_MAX_PATH 256
#define IOTC_RELAY_MAX_CLIENT_ID 64
#define IOTC_RELAY_BUFFER_SIZE 4096

/* Error codes */
typedef enum {
    IOTC_RELAY_SUCCESS = 0,
    IOTC_RELAY_ERROR_SOCKET = -1,
    IOTC_RELAY_ERROR_CONNECT = -2,
    IOTC_RELAY_ERROR_SEND = -3,
    IOTC_RELAY_ERROR_RECV = -4,
    IOTC_RELAY_ERROR_JSON = -5,
    IOTC_RELAY_ERROR_DISCONNECTED = -6,
    IOTC_RELAY_ERROR_INVALID_PARAM = -7
} IotcRelayError;

/* Forward declaration */
typedef struct IotcRelayClient IotcRelayClient;

/**
 * Command callback function type
 */
typedef void (*IotcRelayCommandCallback)(
    const char *command_name,
    const char *command_parameters,
    void *user_data
);

/**
 * Create a new IoTConnect Relay client
 */
IotcRelayClient *iotc_relay_client_create(
    const char *socket_path,
    const char *client_id,
    IotcRelayCommandCallback command_callback,
    void *user_data
);

/**
 * Start the client (connects and starts background threads)
 */
int iotc_relay_client_start(IotcRelayClient *client);

/**
 * Stop the client and clean up resources
 */
void iotc_relay_client_stop(IotcRelayClient *client);

/**
 * Destroy the client and free all resources
 */
void iotc_relay_client_destroy(IotcRelayClient *client);

/**
 * Check if client is connected to the server
 */
bool iotc_relay_client_is_connected(IotcRelayClient *client);

/**
 * Send telemetry data to the server
 * 
 * The data should be a JSON object string, for example:
 *   {"temperature": 25.5, "humidity": 60}
 */
int iotc_relay_client_send_telemetry(
    IotcRelayClient *client,
    const char *json_data
);

/**
 * Get a human-readable error message for an error code
 */
const char *iotc_relay_error_string(int error);

#ifdef __cplusplus
}
#endif

#endif /* IOTC_RELAY_CLIENT_H */
