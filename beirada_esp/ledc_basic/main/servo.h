#ifndef SERVO_H
#define SERVO_H

#include <stdint.h>
#include "esp_err.h"
#include "driver/ledc.h"

// Definição dos Pinos
#define SERVO1_GPIO 20 // vermelho
#define SERVO2_GPIO 7 // verde
#define SERVO3_GPIO 26 // azul

// Parâmetros do Sinal PWM para Servos Padrão (50Hz)
#define SERVO_FREQ          50
#define SERVO_RESOLUTION    LEDC_TIMER_14_BIT
#define SERVO_MAX_DUTY      ((1 << 14) - 1) // 16383 para 14 bits

#define SERVO_MIN_PULSE_US  500   // Pulso mínimo em microsegundos (0 graus)
#define SERVO_MAX_PULSE_US  2500  // Pulso máximo em microsegundos (180 graus)

// Identificador Amigável para os Servos/Atuadores da Esteira
typedef enum {
    servo1 = 0,
    servo2 = 1,
    servo3 = 2,
    SERVO_MAX_COUNT
} servo_id_t;

/**
 * @brief Inicializa os timers e canais LEDC configurados para os servos.
 * @return esp_err_t ESP_OK em caso de sucesso.
 */
esp_err_t servo_init(void);

/**
 * @brief Define o ângulo de um servo específico.
 * 
 * @param id Identificador do servo (servo1, servo2, etc).
 * @param angle_deg Ângulo desejado em graus (0 a 180).
 * @return esp_err_t ESP_OK em caso de sucesso.
 */
esp_err_t servo_angulo(servo_id_t id, uint8_t angle_deg);

/**
 * @brief Desativa um servo específico.
 * 
 * @param id Identificador do servo (servo1, servo2, etc).
 */
void servo_desativar(servo_id_t id);

/**
 * @brief Ativa um servo específico para a posição de abertura.
 * 
 * @param id Identificador do servo (servo1, servo2, etc).
 */
void servo_abrir(servo_id_t id);

#endif // SERVO_H