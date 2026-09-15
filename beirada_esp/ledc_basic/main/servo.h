#ifndef SERVO_H
#define SERVO_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "driver/gpio.h"
#include "driver/ledc.h"

// Pinos dos LEDs/Servos
#define SERVO1_GPIO 20
#define SERVO2_GPIO 7
#define SERVO3_GPIO 26

// Sensores de Entrada (Esteira Principal - Ativam o Servo)
#define SENSOR1_ENTRADA_GPIO 4
#define SENSOR2_ENTRADA_GPIO 38
#define SENSOR3_ENTRADA_GPIO 39

// Sensores de Saída (Esteiras Perpendiculares - Desativam o Servo)
#define SENSOR1_SAIDA_GPIO   5
#define SENSOR2_SAIDA_GPIO   16
#define SENSOR3_SAIDA_GPIO   17

#define SERVO_FREQ          50
#define SERVO_RESOLUTION    LEDC_TIMER_14_BIT
#define SERVO_MAX_DUTY      ((1 << 14) - 1) // 16383 em 14 bits

#define SERVO_MIN_PULSE_US  500   // Pulso mínimo (0 graus)
#define SERVO_MAX_PULSE_US  2500  // Pulso máximo (180 graus)

typedef enum {
    servo1 = 0,
    servo2 = 1,
    servo3 = 2,
    SERVO_MAX_COUNT
} servo_id_t;

typedef enum {
    SENSOR_ENTRADA,
    SENSOR_SAIDA
} sensor_tipo_t;

esp_err_t servo_init(void);
esp_err_t servo_angulo(servo_id_t id, uint8_t angle_deg);
void servo_desativar(servo_id_t id);
void servo_abrir(servo_id_t id);

// Leitura parametrizada por id do servo e tipo de sensor
bool sensor_objeto_presente(servo_id_t id, sensor_tipo_t tipo);

#endif // SERVO_H