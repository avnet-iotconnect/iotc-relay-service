#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>
#include "iotc_relay_client.h"

#define SOCKET_PATH "/tmp/iotconnect-relay.sock"
#define CLIENT_ID "c_data_generator_2"

static const char *NAMES[] = {
    "Andrew", "Beth", "Charles", "Diane", 
    "Eric", "Francis", "George", "Hannah"
};
#define NUM_NAMES (sizeof(NAMES) / sizeof(NAMES[0]))

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

static void generate_random_data(float *number_decimal_negative, const char **name)
{
    *number_decimal_negative = -((float)(rand() % 101) / 100.0f);  /* -1.00 to 0.00 */
    *name = NAMES[rand() % NUM_NAMES];
}

static void get_timestamp(char *buffer, size_t size)
{
    time_t now = time(NULL);
    struct tm *tm_info = localtime(&now);
    strftime(buffer, size, "%Y-%m-%d %H:%M:%S", tm_info);
}

int main(void)
{
    int ret;
    float number_decimal_negative;
    const char *name;
    char timestamp[64];
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
    
    ret = iotc_relay_client_start(g_client);
    if (ret != IOTC_RELAY_SUCCESS) {
        fprintf(stderr, "Failed to start client: %s\n", 
                iotc_relay_error_string(ret));
        iotc_relay_client_destroy(g_client);
        return 1;
    }
    
    while (1) {
        generate_random_data(&number_decimal_negative, &name);
        get_timestamp(timestamp, sizeof(timestamp));
        
        printf("[%s] Number: %.2f, Name: %s\n", timestamp, number_decimal_negative, name);
        
        if (iotc_relay_client_is_connected(g_client)) {
            snprintf(json_buffer, sizeof(json_buffer),
                     "{\"random_number_decimal_negative\":%.2f,\"random_name\":\"%s\"}",
                     number_decimal_negative, name);
            
            ret = iotc_relay_client_send_telemetry(g_client, json_buffer);
            if (ret == IOTC_RELAY_SUCCESS) {
                printf("  → Telemetry sent to server\n");
            } else {
                printf("  → Failed to send telemetry: %s\n", 
                       iotc_relay_error_string(ret));
            }
        } else {
            printf("  → Not connected - data generated locally only\n");
        }
        
        sleep(5);
    }
    
    iotc_relay_client_stop(g_client);
    iotc_relay_client_destroy(g_client);
    
    return 0;
}
