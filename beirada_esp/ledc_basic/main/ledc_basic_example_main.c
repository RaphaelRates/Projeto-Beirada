#include <stdio.h>
#include <stdlib.h>
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



    // 2. Inicializa Filas e Tasks
    if (logica_filas_init() != ESP_OK) {
        ESP_LOGE(TAG, "Erro crítico ao inicializar lógica da esteira.");
        return;
    }

    // --- TESTE INICIAL (uma vez só, para validar servos) ---
    vTaskDelay(pdMS_TO_TICKS(2000));
    servo_abrir(servo1);
    servo_abrir(servo2);
    servo_abrir(servo3);
    vTaskDelay(pdMS_TO_TICKS(3000));
    for (int i = 0; i < SERVO_MAX_COUNT; i++) {
        servo_desativar((servo_id_t)i);
    }

    ESP_LOGI(TAG, "Iniciando loop infinito de simulação...");

    // --- LOOP INFINITO DE CENÁRIOS ---
    uint32_t ciclo = 0;
    while (1) {
        ciclo++;
        ESP_LOGI(TAG, "=== Ciclo %lu ===", (unsigned long)ciclo);

        // Cenário A: ordem "fora de ordem" (3 chega antes de 1)
        // Testa se o servo 1 dispara ANTES do servo 3
        ESP_LOGI(TAG, "Cenario A: pecas 3 -> 1 -> 2");
        peca_para_fila(3);
        vTaskDelay(pdMS_TO_TICKS(500));
        peca_para_fila(1);
        vTaskDelay(pdMS_TO_TICKS(500));
        peca_para_fila(2);

        // Espera o cenário A terminar de ser processado
        vTaskDelay(pdMS_TO_TICKS(6000));

        // Cenário B: sequência normal crescente
        ESP_LOGI(TAG, "Cenario B: pecas 1 -> 2 -> 3");
        for (int i = 1; i <= SERVO_MAX_COUNT; i++) {
            peca_para_fila(i);
            vTaskDelay(pdMS_TO_TICKS(800));
        }
        vTaskDelay(pdMS_TO_TICKS(6000));

        // Cenário C: rajada de peças aleatórias
        ESP_LOGI(TAG, "Cenario C: rajada aleatoria");
        for (int i = 0; i < 10; i++) {
            int peca = (rand() % SERVO_MAX_COUNT) + 1;
            ESP_LOGI(TAG, "  -> peca %d", peca);
            peca_para_fila(peca);
            vTaskDelay(pdMS_TO_TICKS(700));
        }
        vTaskDelay(pdMS_TO_TICKS(8000));

        // Cenário D: mesma peça várias vezes seguidas (stress da fila)
        ESP_LOGI(TAG, "Cenario D: mesma peca repetida");
        int alvo = (rand() % SERVO_MAX_COUNT) + 1;
        for (int i = 0; i < 4; i++) {
            ESP_LOGI(TAG, "  -> peca %d", alvo);
            peca_para_fila(alvo);
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
        vTaskDelay(pdMS_TO_TICKS(8000));

        // Pausa entre ciclos completos
        ESP_LOGI(TAG, "Fim do ciclo %lu, aguardando...", (unsigned long)ciclo);
        vTaskDelay(pdMS_TO_TICKS(3000));
    }
}