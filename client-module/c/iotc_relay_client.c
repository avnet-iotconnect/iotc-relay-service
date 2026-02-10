/*
 * SPDX-License-Identifier: MIT
 * Copyright (C) 2024 Avnet
 * 
 * IoTConnect Relay Client - C Library Implementation
 */

#include "iotc_relay_client.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <errno.h>

/* JSON parsing helpers */
static char *find_json_value(const char *json, const char *key);
static char *create_json_telemetry(const char *client_id, const char *data);
static char *create_json_register(const char *client_id);

/* Client structure */
struct IotcRelayClient {
    char socket_path[IOTC_RELAY_MAX_PATH];
    char client_id[IOTC_RELAY_MAX_CLIENT_ID];
    int sockfd;
    bool is_connected;
    bool is_running;
    pthread_t receive_thread;
    pthread_t reconnect_thread;
    pthread_mutex_t lock;
    IotcRelayCommandCallback command_callback;
    void *user_data;
    int reconnect_delay;
};

/* Forward declarations for thread functions */
static void *receive_thread_func(void *arg);
static void *reconnect_thread_func(void *arg);
static int connect_to_server(IotcRelayClient *client);
static void disconnect_from_server(IotcRelayClient *client);
static int send_message(IotcRelayClient *client, const char *message);
static void handle_server_message(IotcRelayClient *client, const char *message);

IotcRelayClient *iotc_relay_client_create(
    const char *socket_path,
    const char *client_id,
    IotcRelayCommandCallback command_callback,
    void *user_data)
{
    if (!socket_path || !client_id) {
        return NULL;
    }

    IotcRelayClient *client = calloc(1, sizeof(IotcRelayClient));
    if (!client) {
        return NULL;
    }

    strncpy(client->socket_path, socket_path, IOTC_RELAY_MAX_PATH - 1);
    strncpy(client->client_id, client_id, IOTC_RELAY_MAX_CLIENT_ID - 1);
    client->sockfd = -1;
    client->is_connected = false;
    client->is_running = false;
    client->command_callback = command_callback;
    client->user_data = user_data;
    client->reconnect_delay = 5;
    
    pthread_mutex_init(&client->lock, NULL);

    return client;
}

int iotc_relay_client_start(IotcRelayClient *client)
{
    if (!client) {
        return IOTC_RELAY_ERROR_INVALID_PARAM;
    }

    client->is_running = true;

    if (connect_to_server(client) == IOTC_RELAY_SUCCESS) {
        printf("Initial connection successful!\n");
    } else {
        printf("Initial connection failed. Will continue to retry in background...\n");
    }

    if (pthread_create(&client->reconnect_thread, NULL, reconnect_thread_func, client) != 0) {
        fprintf(stderr, "Failed to create reconnect thread\n");
        client->is_running = false;
        return IOTC_RELAY_ERROR_SOCKET;
    }

    return IOTC_RELAY_SUCCESS;
}

void iotc_relay_client_stop(IotcRelayClient *client)
{
    if (!client) {
        return;
    }

    printf("Stopping client...\n");
    client->is_running = false;
    disconnect_from_server(client);

    if (client->receive_thread) {
        pthread_cancel(client->receive_thread);
        pthread_detach(client->receive_thread);
    }
    if (client->reconnect_thread) {
        pthread_cancel(client->reconnect_thread);
        pthread_detach(client->reconnect_thread);
    }
    
    printf("Client stopped.\n");
}

void iotc_relay_client_destroy(IotcRelayClient *client)
{
    if (!client) {
        return;
    }

    iotc_relay_client_stop(client);
    pthread_mutex_destroy(&client->lock);
    free(client);
}

bool iotc_relay_client_is_connected(IotcRelayClient *client)
{
    bool connected;
    
    if (!client) {
        return false;
    }

    pthread_mutex_lock(&client->lock);
    connected = client->is_connected;
    pthread_mutex_unlock(&client->lock);

    return connected;
}

int iotc_relay_client_send_telemetry(IotcRelayClient *client, const char *json_data)
{
    char *message;
    int result;
    
    if (!client || !json_data) {
        return IOTC_RELAY_ERROR_INVALID_PARAM;
    }

    pthread_mutex_lock(&client->lock);

    if (!client->is_connected) {
        pthread_mutex_unlock(&client->lock);
        return IOTC_RELAY_ERROR_DISCONNECTED;
    }

    message = create_json_telemetry(client->client_id, json_data);
    if (!message) {
        pthread_mutex_unlock(&client->lock);
        return IOTC_RELAY_ERROR_JSON;
    }

    result = send_message(client, message);
    free(message);

    pthread_mutex_unlock(&client->lock);

    return result;
}

const char *iotc_relay_error_string(int error)
{
    switch (error) {
        case IOTC_RELAY_SUCCESS:
            return "Success";
        case IOTC_RELAY_ERROR_SOCKET:
            return "Socket error";
        case IOTC_RELAY_ERROR_CONNECT:
            return "Connection error";
        case IOTC_RELAY_ERROR_SEND:
            return "Send error";
        case IOTC_RELAY_ERROR_RECV:
            return "Receive error";
        case IOTC_RELAY_ERROR_JSON:
            return "JSON error";
        case IOTC_RELAY_ERROR_DISCONNECTED:
            return "Not connected";
        case IOTC_RELAY_ERROR_INVALID_PARAM:
            return "Invalid parameter";
        default:
            return "Unknown error";
    }
}

/**
 * Parse a "tcp://host:port" string.
 * Returns 1 on success (host and port filled in), 0 if not a tcp:// path.
 */
static int parse_tcp_target(const char *path, char *host, size_t host_len, int *port)
{
    const char *prefix = "tcp://";
    const char *start;
    const char *colon;

    if (strncmp(path, prefix, strlen(prefix)) != 0) {
        return 0;
    }

    start = path + strlen(prefix);
    colon = strrchr(start, ':');
    if (!colon || colon == start) {
        return 0;
    }

    size_t hlen = (size_t)(colon - start);
    if (hlen >= host_len) {
        hlen = host_len - 1;
    }
    strncpy(host, start, hlen);
    host[hlen] = '\0';
    *port = atoi(colon + 1);

    return 1;
}

static int connect_to_server(IotcRelayClient *client)
{
    char *reg_msg;
    char host[256];
    int port;

    if (parse_tcp_target(client->socket_path, host, sizeof(host), &port)) {
        /* TCP connection */
        struct sockaddr_in tcp_addr;

        client->sockfd = socket(AF_INET, SOCK_STREAM, 0);
        if (client->sockfd < 0) {
            return IOTC_RELAY_ERROR_SOCKET;
        }

        memset(&tcp_addr, 0, sizeof(tcp_addr));
        tcp_addr.sin_family = AF_INET;
        tcp_addr.sin_port = htons((uint16_t)port);

        if (inet_pton(AF_INET, host, &tcp_addr.sin_addr) <= 0) {
            /* Try resolving as hostname */
            struct hostent *he = gethostbyname(host);
            if (!he) {
                close(client->sockfd);
                client->sockfd = -1;
                return IOTC_RELAY_ERROR_CONNECT;
            }
            memcpy(&tcp_addr.sin_addr, he->h_addr_list[0], (size_t)he->h_length);
        }

        if (connect(client->sockfd, (struct sockaddr *)&tcp_addr, sizeof(tcp_addr)) < 0) {
            close(client->sockfd);
            client->sockfd = -1;
            return IOTC_RELAY_ERROR_CONNECT;
        }

        printf("Connected to IoTConnect Relay server via TCP at %s:%d\n", host, port);
    } else {
        /* Unix socket connection */
        struct sockaddr_un addr;

        client->sockfd = socket(AF_UNIX, SOCK_STREAM, 0);
        if (client->sockfd < 0) {
            return IOTC_RELAY_ERROR_SOCKET;
        }

        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, client->socket_path, sizeof(addr.sun_path) - 1);

        if (connect(client->sockfd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
            close(client->sockfd);
            client->sockfd = -1;
            return IOTC_RELAY_ERROR_CONNECT;
        }

        printf("Connected to IoTConnect Relay server at %s\n", client->socket_path);
    }

    pthread_mutex_lock(&client->lock);
    client->is_connected = true;
    pthread_mutex_unlock(&client->lock);

    reg_msg = create_json_register(client->client_id);
    if (reg_msg) {
        send_message(client, reg_msg);
        free(reg_msg);
    }

    if (pthread_create(&client->receive_thread, NULL, receive_thread_func, client) != 0) {
        fprintf(stderr, "Failed to create receive thread\n");
        disconnect_from_server(client);
        return IOTC_RELAY_ERROR_SOCKET;
    }

    return IOTC_RELAY_SUCCESS;
}

static void disconnect_from_server(IotcRelayClient *client)
{
    pthread_mutex_lock(&client->lock);
    client->is_connected = false;
    
    if (client->sockfd >= 0) {
        close(client->sockfd);
        client->sockfd = -1;
    }
    
    pthread_mutex_unlock(&client->lock);
}

static int send_message(IotcRelayClient *client, const char *message)
{
    size_t len = strlen(message);
    ssize_t sent = send(client->sockfd, message, len, 0);
    
    if (sent < 0 || (size_t)sent != len) {
        client->is_connected = false;
        return IOTC_RELAY_ERROR_SEND;
    }

    return IOTC_RELAY_SUCCESS;
}

static void handle_server_message(IotcRelayClient *client, const char *message)
{
    char *type;
    char *command_name;
    char *parameters;
    
    type = find_json_value(message, "type");
    if (!type) {
        return;
    }

    if (strcmp(type, "command") == 0) {
        command_name = find_json_value(message, "command_name");
        parameters = find_json_value(message, "parameters");
        
        if (command_name && client->command_callback) {
            client->command_callback(
                command_name,
                parameters ? parameters : "",
                client->user_data
            );
        }

        free(command_name);
        free(parameters);
    }

    free(type);
}

static void *receive_thread_func(void *arg)
{
    IotcRelayClient *client = (IotcRelayClient *)arg;
    char buffer[IOTC_RELAY_BUFFER_SIZE];
    char message_buffer[IOTC_RELAY_BUFFER_SIZE * 2] = {0};
    ssize_t received;
    char *newline;
    
    while (client->is_running && client->is_connected) {
        received = recv(client->sockfd, buffer, sizeof(buffer) - 1, 0);
        
        if (received <= 0) {
            printf("Server closed connection\n");
            pthread_mutex_lock(&client->lock);
            client->is_connected = false;
            pthread_mutex_unlock(&client->lock);
            break;
        }

        buffer[received] = '\0';
        strncat(message_buffer, buffer, sizeof(message_buffer) - strlen(message_buffer) - 1);

        while ((newline = strchr(message_buffer, '\n')) != NULL) {
            *newline = '\0';
            
            handle_server_message(client, message_buffer);
            
            memmove(message_buffer, newline + 1, strlen(newline + 1) + 1);
        }
    }

    return NULL;
}

static void *reconnect_thread_func(void *arg)
{
    IotcRelayClient *client = (IotcRelayClient *)arg;
    
    while (client->is_running) {
        if (!client->is_connected) {
            if (connect_to_server(client) == IOTC_RELAY_SUCCESS) {
                printf("Reconnection successful!\n");
            }
        }
        sleep(client->reconnect_delay);
    }

    return NULL;
}

static char *find_json_value(const char *json, const char *key)
{
    char search[128];
    const char *start;
    const char *end;
    size_t len;
    char *value;
    char *p;
    
    snprintf(search, sizeof(search), "\"%s\":", key);
    
    start = strstr(json, search);
    if (!start) {
        return NULL;
    }
    
    start += strlen(search);
    
    while (*start == ' ' || *start == '\t') {
        start++;
    }
    
    if (*start == '"') {
        start++;
        end = strchr(start, '"');
        if (!end) {
            return NULL;
        }
        
        len = end - start;
        value = malloc(len + 1);
        if (value) {
            strncpy(value, start, len);
            value[len] = '\0';
        }
        return value;
    }
    
    end = start;
    while (*end && *end != ',' && *end != '}' && *end != '\n') {
        end++;
    }
    
    len = end - start;
    value = malloc(len + 1);
    if (value) {
        strncpy(value, start, len);
        value[len] = '\0';
        
        p = value + len - 1;
        while (p > value && (*p == ' ' || *p == '\t')) {
            *p-- = '\0';
        }
    }
    
    return value;
}

static char *create_json_telemetry(const char *client_id, const char *data)
{
    size_t len = 256 + strlen(client_id) + strlen(data);
    char *json = malloc(len);
    if (!json) {
        return NULL;
    }

    snprintf(json, len,
             "{\"type\":\"telemetry\",\"client_id\":\"%s\",\"data\":%s}\n",
             client_id, data);

    return json;
}

static char *create_json_register(const char *client_id)
{
    size_t len = 128 + strlen(client_id);
    char *json = malloc(len);
    if (!json) {
        return NULL;
    }

    snprintf(json, len,
             "{\"type\":\"register\",\"client_id\":\"%s\"}\n",
             client_id);

    return json;
}
