#include "filas.h"
#include "servo.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"

static const char *TAG = "LOGICA_FILAS";

static QueueHandle_t xServoQueues[SERVO_MAX_COUNT];

static void servo_task(void *pvParameters)
{
    servo_id_t servo_id = (servo_id_t)(uintptr_t)pvParameters;
    uint8_t piece_class;
    uint8_t my_target_class = (uint8_t)(servo_id + 1); // Servo 1 quer classe 1, Servo 2 quer classe 2, etc.

    ESP_LOGI(TAG, "Task do Servo %d rodando (Modo Sincronizado por Passagem).", servo_id + 1);

    while (1) {
        // 1. Aguarda a próxima peça da fila do seu trecho da esteira
        if (xQueueReceive(xServoQueues[servo_id], &piece_class, portMAX_DELAY) == pdTRUE) {

            ESP_LOGI(TAG, "Servo %d: Peça classe %d a caminho. Aguardando no Sensor de ENTRADA...", 
                     servo_id + 1, piece_class);

            // 2. Aguarda a peça FISICAMENTE chegar ao sensor de entrada deste servo
            while (!sensor_objeto_presente(servo_id, SENSOR_ENTRADA)) {
                vTaskDelay(pdMS_TO_TICKS(100));
            }

            // 3. A peça chegou no sensor! Verificamos se ela é DESTINADA a este servo
            if (piece_class == my_target_class) {
                // É MINHA PEÇA! Ativa o desvio
                ESP_LOGI(TAG, ">> Servo %d: Peça correspondente (%d) detectada! ACIONANDO BRAÇO.", 
                         servo_id + 1, piece_class);

                // Aguarda confirmação no sensor de saída (esteira perpendicular)
                while (!sensor_objeto_presente(servo_id, SENSOR_SAIDA)) {
                    if (servo_id == servo2) {
                        servo_angulo(servo_id, 50);
                        vTaskDelay(pdMS_TO_TICKS(100));
                        servo_angulo(servo_id, 60);
                        vTaskDelay(pdMS_TO_TICKS(100));
                        servo_angulo(servo_id, 50);
                    } else {
                        servo_angulo(servo_id, 150);
                        vTaskDelay(pdMS_TO_TICKS(100));
                        servo_angulo(servo_id, 140);
                        vTaskDelay(pdMS_TO_TICKS(100));
                        servo_angulo(servo_id, 150);
                    }
                }

                vTaskDelay(pdMS_TO_TICKS(150));
                servo_desativar(servo_id);
                ESP_LOGI(TAG, ">> Servo %d: Peça transferida com sucesso.", servo_id + 1);

            } else {
                // NÃO É MINHA PEÇA! Apenas aguarda ela PASSAR do sensor de entrada e deixa seguir em frente
                ESP_LOGI(TAG, "-- Servo %d: Peça classe %d é para outro servo. IGNORANDO e mantendo fechado.", 
                         servo_id + 1, piece_class);

                // Aguarda a peça sair da frente do sensor de entrada antes de liberar a fila para a próxima
                while (sensor_objeto_presente(servo_id, SENSOR_ENTRADA)) {
                    vTaskDelay(pdMS_TO_TICKS(100));
                }
                
                vTaskDelay(pdMS_TO_TICKS(200)); // Pequena margem de desobstrução
            }
        }
    }
}

esp_err_t logica_filas_init(void)
{
    char task_name[16];

    for (int i = 0; i < SERVO_MAX_COUNT; i++) {
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

    ESP_LOGI(TAG, "Lógica da esteira inicializada com controle de passagem.");
    return ESP_OK;
}

void peca_para_fila(uint8_t piece_class)
{
    if (piece_class < 1 || piece_class > SERVO_MAX_COUNT) {
        ESP_LOGW(TAG, "Classe inválida recebida: %d", piece_class);
        return;
    }

    // Envia a peça SOMENTE para os servos pelos quais ela precisa passar até chegar ao seu destino
    // Ex: Peça 3 precisa passar pelo Servo 1, Servo 2 e Servo 3 (i = 0, 1, 2)
    // Ex: Peça 1 precisa passar apenas pelo Servo 1 (i = 0)
    for (int i = 0; i < piece_class; i++) {
        if (xQueueSend(xServoQueues[i], &piece_class, pdMS_TO_TICKS(100)) != pdTRUE) {
            ESP_LOGE(TAG, "Fila do Servo %d cheia! Peça %d descartada.", i + 1, piece_class);
        } else {
            ESP_LOGI(TAG, "Peça classe %d registrada na fila do Servo %d.", piece_class, i + 1);
        }
    }
}