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

    while (1) {
        // 1. Aguarda a visão computacional informar que há uma peça encaminhada para este servo
        if (xQueueReceive(xServoQueues[servo_id], &piece_class, portMAX_DELAY) == pdTRUE) {
            
            ESP_LOGI(TAG, "Servo %d aguardando a chegada da peça no sensor...", servo_id + 1);

            // 2. Aguarda a peça FISICAMENTE CHEGAR ao sensor (Borda de Descida)
            while (!sensor_objeto_presente(servo_id)) {
                vTaskDelay(pdMS_TO_TICKS(10));
            }

            // 3. Peça chegou! Ativa o servo para desviar
            ESP_LOGI(TAG, "Peça detectada pelo Sensor %d! Acionando servo...", servo_id + 1);
            servo_abrir(servo_id);

            // 4. Aguarda a peça SAIR COMPLETAMENTE do sensor (Borda de Subida)
            // O servo continua aberto enquanto a peça bloquear o feixe
            while (sensor_objeto_presente(servo_id)) {
                vTaskDelay(pdMS_TO_TICKS(10));
            }

            // Opcional: Pequeno atraso extra (ex: 100ms) só para garantir o término da física do desvio
            vTaskDelay(pdMS_TO_TICKS(100));

            // 5. Desativa o servo, retornando à posição de repouso
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