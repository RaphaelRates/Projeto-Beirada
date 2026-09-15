#include <stdio.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "servo.h"
#include "filas.h"
#include "serial.h"



static const char *TAG = "MAIN";

void app_main(void)
{
    ESP_LOGI(TAG, "Iniciando Sistema de Controle da Esteira...");

    if (servo_init() != ESP_OK) {
        ESP_LOGE(TAG, "Erro crítico ao inicializar servos.");
        return;
    }

    if (logica_filas_init() != ESP_OK) {
        ESP_LOGE(TAG, "Erro crítico ao inicializar lógica da esteira.");
        return;
    }

    if (serial_init() != ESP_OK) {
        ESP_LOGE(TAG, "Erro crítico ao inicializar comunicação UART.");
        return;
    }

    vTaskDelay(pdMS_TO_TICKS(1000));
    ESP_LOGI(TAG, "Sistema pronto para receber classes via UART e acionar os sensores/servos.");

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(200));
    }
}