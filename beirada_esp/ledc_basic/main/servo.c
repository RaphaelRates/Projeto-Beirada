#include "servo.h"
#include "esp_log.h"
#include "driver/gpio.h"

static const char *TAG = "SERVO_CONTROL";

// Estrutura para associar o ID do servo ao pino e ao canal do LEDC
typedef struct {
    gpio_num_t gpio;
    ledc_channel_t channel;
} servo_config_t;

// Instanciação do array servos (Mapeia ID -> Pino GPIO e Canal LEDC)
static const servo_config_t servos[SERVO_MAX_COUNT] = {
    [servo1] = { .gpio = SERVO1_GPIO, .channel = LEDC_CHANNEL_0 },
    [servo2] = { .gpio = SERVO2_GPIO, .channel = LEDC_CHANNEL_1 },
    [servo3] = { .gpio = SERVO3_GPIO, .channel = LEDC_CHANNEL_2 },
};

static const gpio_num_t sensores_entrada[SERVO_MAX_COUNT] = {
    [servo1] = SENSOR1_ENTRADA_GPIO,
    [servo2] = SENSOR2_ENTRADA_GPIO,
    [servo3] = SENSOR3_ENTRADA_GPIO,
};

static const gpio_num_t sensores_saida[SERVO_MAX_COUNT] = {
    [servo1] = SENSOR1_SAIDA_GPIO,
    [servo2] = SENSOR2_SAIDA_GPIO,
    [servo3] = SENSOR3_SAIDA_GPIO,
};

esp_err_t servo_init(void)
{
    // 1. Configuração do Timer do LEDC
    ledc_timer_config_t timer_config = {
        .speed_mode       = LEDC_LOW_SPEED_MODE,
        .timer_num        = LEDC_TIMER_0,
        .duty_resolution  = SERVO_RESOLUTION,
        .freq_hz          = SERVO_FREQ,
        .clk_cfg          = LEDC_AUTO_CLK
    };
    ledc_timer_config(&timer_config);

    // Configuração dos Canais LEDC usando o array servos
    for (int i = 0; i < SERVO_MAX_COUNT; i++) {
        ledc_channel_config_t channel_config = {
            .gpio_num   = servos[i].gpio,
            .speed_mode = LEDC_LOW_SPEED_MODE,
            .channel    = servos[i].channel,
            .timer_sel  = LEDC_TIMER_0,
            .duty       = 0,
            .hpoint     = 0
        };
        ledc_channel_config(&channel_config);
    }

    // 2. Configuração dos 6 Sensores (3 Entradas + 3 Saídas)
    uint64_t sensor_mask = (1ULL << SENSOR1_ENTRADA_GPIO) | (1ULL << SENSOR2_ENTRADA_GPIO) | (1ULL << SENSOR3_ENTRADA_GPIO) |
                           (1ULL << SENSOR1_SAIDA_GPIO)   | (1ULL << SENSOR2_SAIDA_GPIO)   | (1ULL << SENSOR3_SAIDA_GPIO);

    gpio_config_t io_conf_in = {
        .pin_bit_mask = sensor_mask,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE
    };
    gpio_config(&io_conf_in);

    for (int i = 0; i < SERVO_MAX_COUNT; i++) {
        servo_desativar((servo_id_t)i);
    }

    ESP_LOGI(TAG, "Servos e 6 Sensores E18 inicializados!");
    return ESP_OK;
}

bool sensor_objeto_presente(servo_id_t id, sensor_tipo_t tipo)
{
    if (id >= SERVO_MAX_COUNT) return false;

    gpio_num_t pino = (tipo == SENSOR_ENTRADA) ? sensores_entrada[id] : sensores_saida[id];
    return (gpio_get_level(pino) == 0); // 0 (LOW) = Objeto detectado
}

esp_err_t servo_angulo(servo_id_t id, uint8_t angle_deg)
{
    if (id >= SERVO_MAX_COUNT) {
        ESP_LOGE(TAG, "ID de servo inválido: %d", id);
        return ESP_ERR_INVALID_ARG;
    }

    if (angle_deg > 180) {
        angle_deg = 180;
    }

    // Cálculo do tempo de pulso em us (500us a 2500us)
    uint32_t pulse_us = SERVO_MIN_PULSE_US + 
        ((SERVO_MAX_PULSE_US - SERVO_MIN_PULSE_US) * angle_deg) / 180;

    // Converte microsegundos para o equivalente em Duty Cycle (Timer 14-bit @ 50Hz)
    uint32_t duty = (pulse_us * SERVO_MAX_DUTY) / 20000;

    esp_err_t err = ledc_set_duty(LEDC_LOW_SPEED_MODE, servos[id].channel, duty);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Erro ao definir duty no servo %d: %s", id, esp_err_to_name(err));
        return err;
    }

    err = ledc_update_duty(LEDC_LOW_SPEED_MODE, servos[id].channel);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Erro ao atualizar duty no servo %d: %s", id, esp_err_to_name(err));
        return err;
    }

    return ESP_OK;
}

void servo_desativar(servo_id_t id)
{
    servo_angulo(id, 90); // Posição de repouso (paralelo à esteira)
}

void servo_abrir(servo_id_t id)
{
    if (id == servo2) {
        servo_angulo(id, 50);
    } else {
        servo_angulo(id, 150);
    }
}

/*#include "servo.h"
#include "driver/gpio.h"
#include "esp_log.h"

static const char *TAG = "SERVO_LEDS";

// Mapeamento dos pinos dos LEDs simuladores
static const gpio_num_t servo_gpios[SERVO_MAX_COUNT] = {
    [servo1] = SERVO1_GPIO,
    [servo2] = SERVO2_GPIO,
    [servo3] = SERVO3_GPIO,
};

esp_err_t servo_init(void)
{
    // Configura os pinos como saídas digitais simples
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << SERVO1_GPIO) | (1ULL << SERVO2_GPIO) | (1ULL << SERVO3_GPIO),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE
    };

    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Falha ao configurar GPIOs dos LEDs: %s", esp_err_to_name(err));
        return err;
    }

    // Garante que todos iniciem apagaods
    for (int i = 0; i < SERVO_MAX_COUNT; i++) {
        servo_desativar((servo_id_t)i);
    }

    ESP_LOGI(TAG, "Módulo de LEDs (Simuladores de Servo) inicializado!");
    return ESP_OK;
}

esp_err_t servo_angulo(servo_id_t id, uint8_t angle_deg)
{
    // Mantida apenas para compatibilidade de assinatura no header
    return ESP_OK;
}

void servo_desativar(servo_id_t id)
{
    if (id < SERVO_MAX_COUNT) {
        gpio_set_level(servo_gpios[id], 0); // APAGA O LED
        ESP_LOGI(TAG, "LED %d APAGADO (Servo em Repouso)", id + 1);
    }
}

void servo_abrir(servo_id_t id)
{
    if (id < SERVO_MAX_COUNT) {
        gpio_set_level(servo_gpios[id], 1); // ACENDE O LED
        ESP_LOGI(TAG, "LED %d ACESO (Servo Acionado)", id + 1);
    }
}*/