/* LEDC (LED Controller) basic example

   This example code is in the Public Domain (or CC0 licensed, at your option.)

   Unless required by applicable law or agreed to in writing, this
   software is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
   CONDITIONS OF ANY KIND, either express or implied.
*/
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "servo.h"
#include "filas.h"

static const char *TAG = "MAIN";

void app_main(void)
{
    ESP_LOGI(TAG, "Iniciando Sistema de Controle da Esteira...");

    // 1. Inicializa Servos
    if (servo_init() != ESP_OK) {
        ESP_LOGE(TAG, "Erro crítico ao inicializar servos.");
        return;
    }

    // Coloca todos os servos em repouso
    for (int i = 0; i < SERVO_MAX_COUNT; i++) {
        servo_desativar((servo_id_t)i);
    }

    // 2. Inicializa Filas e Tasks
    if (logica_filas_init() != ESP_OK) {
        ESP_LOGE(TAG, "Erro crítico ao inicializar lógica da esteira.");
        return;
    }

    // --- TESTE DE SIMULAÇÃO DE PEÇAS NO FLUXO ---
    vTaskDelay(pdMS_TO_TICKS(2000));

    servo_abrir(servo1);
    servo_abrir(servo2);
    servo_abrir(servo3);
    vTaskDelay(pdMS_TO_TICKS(3000));

    for (int i = 0; i < SERVO_MAX_COUNT; i++) {
        servo_desativar((servo_id_t)i);
    }
    
    // Simula: Peça 3 detectada t=0ms (Servo 3 deve acionar em t=4500ms)
    peca_para_fila(3);

    // Simula: Peça 1 detectada t=500ms (Servo 1 deve acionar em t=2000ms, ANTES da Peça 3!)
    vTaskDelay(pdMS_TO_TICKS(500));
    peca_para_fila(1);

    peca_para_fila(2);

    for (int i = 0; i < 30; i++) {
        peca_para_fila(rand() % 3 + 1); // Peças aleatórias entre 1 e 3
        vTaskDelay(pdMS_TO_TICKS(1500));
    }

}