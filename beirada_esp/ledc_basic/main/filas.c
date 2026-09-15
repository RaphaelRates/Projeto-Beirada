#include "filas.h"
#include "servo.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"

static const char *TAG = "LOGICA_FILAS";

#define SERVO_ACTION_TIME_MS 1000

static QueueHandle_t xServoQueues[SERVO_MAX_COUNT];

static void servo_task(void *pvParameters)
{
    servo_id_t servo_id = (servo_id_t)(uintptr_t)pvParameters;
    uint8_t piece_class;

    ESP_LOGI(TAG, "Task do Servo %d rodando (Modo Duplo Sensor).", servo_id + 1);

    while (1) {
        // 1. Aguarda a visão informar que há uma peça para este servo
        if (xQueueReceive(xServoQueues[servo_id], &piece_class, portMAX_DELAY) == pdTRUE) {
            
            ESP_LOGI(TAG, "Servo %d aguardando peça no Sensor de ENTRADA...", servo_id + 1);

            // 2. Aguarda o SENSOR DE ENTRADA (esteira principal) detectar a peça
            while (!sensor_objeto_presente(servo_id, SENSOR_ENTRADA)) {
                vTaskDelay(pdMS_TO_TICKS(10));
            }

            // 3. Peça chegou! Ativa o servo para empurrar/desviar
            ESP_LOGI(TAG, "Peça na entrada do Servo %d! Acionando braço...", servo_id + 1);
            servo_abrir(servo_id);

            // 4. Aguarda o SENSOR DE SAÍDA (esteira perpendicular) confirmar a recepção
            ESP_LOGI(TAG, "Aguardando confirmação no Sensor de SAÍDA %d...", servo_id + 1);
            while (!sensor_objeto_presente(servo_id, SENSOR_SAIDA)) {
                vTaskDelay(pdMS_TO_TICKS(10));
            }

            // Pequeno delay opcional para a peça estabilizar na nova esteira
            vTaskDelay(pdMS_TO_TICKS(150));

            // 5. Peça transferida com sucesso! Recolhe o servo
            ESP_LOGI(TAG, "Peça recebida na esteira perpendicular %d! Recolhendo servo.", servo_id + 1);
            servo_desativar(servo_id);
        }
    }
}

esp_err_t logica_filas_init(void)
{
    char task_name[16];

    for (int i = 0; i < SERVO_MAX_COUNT; i++) {
        // guardar apenas o ID/Classe simples (1 byte)
        xServoQueues[i] = xQueueCreate(10, sizeof(uint8_t));
        if (xServoQueues[i] == NULL) {
            return ESP_FAIL;
        }

        snprintf(task_name, sizeof(task_name), "servo_task_%d", i + 1);

        xTaskCreate(
            servo_task,
            task_name,
            2048,
            (void *)(uintptr_t)i,
            5,
            NULL
        );
    }

    ESP_LOGI(TAG, "Lógica com sensores e filas inicializada com sucesso.");
    return ESP_OK;
}

void peca_para_fila(uint8_t piece_class)
{
    if (piece_class < 1 || piece_class > SERVO_MAX_COUNT) {
        ESP_LOGW(TAG, "Classe inválida recebida: %d", piece_class);
        return;
    }

    servo_id_t target_servo = (servo_id_t)(piece_class - 1);

    // Insere diretamente na fila correspondente
    if (xQueueSend(xServoQueues[target_servo], &piece_class, pdMS_TO_TICKS(100)) != pdTRUE) {
        ESP_LOGE(TAG, "Fila do Servo %d cheia! Peça descartada.", target_servo + 1);
    } else {
        ESP_LOGI(TAG, "Peça classe %d enfileirada para aguardar no Sensor %d", piece_class, target_servo + 1);
    }
}