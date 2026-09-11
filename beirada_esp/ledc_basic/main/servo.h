#ifndef SERVO_H
#define SERVO_H

#include <stdint.h>
#include "esp_err.h"
#include "driver/ledc.h"
#include "driver/gpio.h"

// Definição dos Pinos
#define SERVO1_GPIO 20 // vermelho
#define SERVO2_GPIO 7 // verde
#define SERVO3_GPIO 26 // azul

#define SENSOR1_GPIO 4
#define SENSOR2_GPIO 5
#define SENSOR3_GPIO 6

// Parâmetros do Sinal PWM para Servos Padrão (50Hz)
#define SERVO_FREQ          50
#define SERVO_RESOLUTION    LEDC_TIMER_14_BIT
#define SERVO_MAX_DUTY      ((1 << 14) - 1) // 16383 para 14 bits

#define SERVO_MIN_PULSE_US  500   // Pulso mínimo em microsegundos (0 graus)
#define SERVO_MAX_PULSE_US  2500  // Pulso máximo em microsegundos (180 graus)

// Identificador para os Servos/Atuadores da Esteira
typedef enum {
    servo1 = 0,
    servo2 = 1,
    servo3 = 2,
    SERVO_MAX_COUNT
} servo_id_t;


esp_err_t servo_init(void);
esp_err_t servo_angulo(servo_id_t id, uint8_t angle_deg);
void servo_desativar(servo_id_t id);
void servo_abrir(servo_id_t id);

// Nova função para ler a presença da peça no sensor
bool sensor_objeto_presente(servo_id_t id);

#endif // SERVO_H