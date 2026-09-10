#include "filas.h"
#include "servo.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"

static const char *TAG = "Lógica de filas:";

// Distâncias da câmera até cada servo em metros
const float distancia1 = 1.5; // Levará 1.5 segundos (1500 ms)
const float distancia2 = 3.0; // Levará 3.0 segundos (3000 ms)
const float distancia3 = 4.5; // Levará 4.5 segundos (4500 ms)

const float velocidade = 1.0; // Velocidade da esteira em metros por segundo

static const uint32_t SERVO_TRAVEL_TIME_MS[SERVO_MAX_COUNT] = {
    (uint32_t)((distancia1 / velocidade) * 1000), // Servo 1: 1500ms
    (uint32_t)((distancia2 / velocidade) * 1000), // Servo 2: 3000ms
    (uint32_t)((distancia3 / velocidade) * 1000)  // Servo 3: 4500ms
};

typedef struct {
    uint8_t piece_class;
    TickType_t detection_time;
} conveyor_item_t;

#define SERVO_ACTION_TIME_MS 500

static QueueHandle_t xServoQueues[SERVO_MAX_COUNT];

static void servo_task(void *pvParameters)
{
    servo_id_t servo_id = (servo_id_t)(uintptr_t)pvParameters;
    conveyor_item_t item;

    ESP_LOGI(TAG, "Task do Servo %d rodando.", servo_id + 1);

    while (1) {
        if (xQueueReceive(xServoQueues[servo_id], &item, portMAX_DELAY) == pdTRUE) {
            
            TickType_t now = xTaskGetTickCount();
            TickType_t elapsed_ticks = now - item.detection_time;
            TickType_t target_delay_ticks = pdMS_TO_TICKS(SERVO_TRAVEL_TIME_MS[servo_id]);

            if (target_delay_ticks > elapsed_ticks) {
                vTaskDelay(target_delay_ticks - elapsed_ticks);
            }

            ESP_LOGI(TAG, "Acionando Servo %d para a classe %d", servo_id + 1, item.piece_class);

            servo_abrir(servo_id);
            vTaskDelay(pdMS_TO_TICKS(SERVO_ACTION_TIME_MS));
            servo_desativar(servo_id);
        }
    }
}

esp_err_t logica_filas_init(void)
{
    char task_name[16];

    for (int i = 0; i < SERVO_MAX_COUNT; i++) {
        xServoQueues[i] = xQueueCreate(10, sizeof(conveyor_item_t));
        if (xServoQueues[i] == NULL) {
            ESP_LOGE(TAG, "Falha ao criar fila para o servo %d", i + 1);
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

    ESP_LOGI(TAG, "Lógica da esteira e filas inicializadas.");
    return ESP_OK;
}

void peca_para_fila(uint8_t piece_class)
{
    if (piece_class < 1 || piece_class > SERVO_MAX_COUNT) {
        ESP_LOGW(TAG, "Classe inválida recebida: %d", piece_class);
        return;
    }

    servo_id_t target_servo = (servo_id_t)(piece_class - 1);

    conveyor_item_t item = {
        .piece_class = piece_class,
        .detection_time = xTaskGetTickCount()
    };

    if (xQueueSend(xServoQueues[target_servo], &item, pdMS_TO_TICKS(100)) != pdTRUE) {
        ESP_LOGE(TAG, "Fila do Servo %d cheia! Peça descartada.", target_servo + 1);
    } else {
        ESP_LOGI(TAG, "Peça classe %d enfileirada no Servo %d", piece_class, target_servo + 1);
    }
}