/* LEDC (LED Controller) basic example

   This example code is in the Public Domain (or CC0 licensed, at your option.)

   Unless required by applicable law or agreed to in writing, this
   software is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
   CONDITIONS OF ANY KIND, either express or implied.
*/
#include <stdio.h>
#include "driver/ledc.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

/*#define LEDC_TIMER              LEDC_TIMER_0
#define LEDC_MODE               LEDC_LOW_SPEED_MODE
#define LEDC_OUTPUT_IO          (5) // Define the output GPIO
#define LEDC_CHANNEL            LEDC_CHANNEL_0
#define LEDC_DUTY_RES           LEDC_TIMER_13_BIT // Set duty resolution to 13 bits
#define LEDC_DUTY               (4096) // Set duty to 50%. (2 ** 13) * 50% = 4096
#define LEDC_FREQUENCY          (4000) // Frequency in Hertz. Set frequency at 4 kHz
*/

/* Warning:
 * For ESP32, ESP32S2, ESP32S3, ESP32C3, ESP32C2, ESP32C6, ESP32H2 (rev < 1.2), ESP32P4 (rev < 3.0) targets,
 * when LEDC_DUTY_RES selects the maximum duty resolution (i.e. value equal to SOC_LEDC_TIMER_BIT_WIDTH),
 * 100% duty cycle is not reachable (duty cannot be set to (2 ** SOC_LEDC_TIMER_BIT_WIDTH)).
 */

#define SERVO1_GPIO 20
#define SERVO2_GPIO 14
#define SERVO3_GPIO 21

#define SERVO_FREQ 50
#define SERVO_RESOLUTION LEDC_TIMER_14_BIT

#define SERVO_MIN_PULSE 500
#define SERVO_MAX_PULSE 2500

static void servo_init(void)
{
    ledc_timer_config_t timer_config = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .timer_num = LEDC_TIMER_0,
        .duty_resolution = SERVO_RESOLUTION,
        .freq_hz = SERVO_FREQ,
        .clk_cfg = LEDC_AUTO_CLK
    };

    ledc_timer_config(&timer_config);

    ledc_channel_config_t channel1 = {
        .gpio_num = SERVO1_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0,
        .hpoint = 0
    };

    ledc_channel_config_t channel2 = {
        .gpio_num = SERVO2_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_1,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0,
        .hpoint = 0
    };

    ledc_channel_config_t channel3 = {
        .gpio_num = SERVO3_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_2,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0,
        .hpoint = 0
    };

    ledc_channel_config(&channel1);
    ledc_channel_config(&channel2);
    ledc_channel_config(&channel3);
}

static void servo_write(int channel, int angle)
{
    if (angle < 0)
        angle = 0;



    int pulse_us =
        SERVO_MIN_PULSE +
        ((SERVO_MAX_PULSE - SERVO_MIN_PULSE) * angle) / 180;

    uint32_t duty =
        ((uint32_t)pulse_us * 16383) / 20000;

    esp_err_t err;

    err = ledc_set_duty(
        LEDC_LOW_SPEED_MODE,
        channel,
        duty
    );

    if (err != ESP_OK) {
        printf("Erro ledc_set_duty: %d\n", err);
        return;
    }

    err = ledc_update_duty(
        LEDC_LOW_SPEED_MODE,
        channel
    );

    if (err != ESP_OK) {
        printf("Erro ledc_update_duty: %d\n", err);
    }
}



void app_main(void)
{
    servo_init();

    while (1)
    {
        servo_write(0, 90);
        servo_write(1, 90);
        servo_write(2, 90);
        vTaskDelay(pdMS_TO_TICKS(2000));

        servo_write(0, 50);
        vTaskDelay(pdMS_TO_TICKS(2000));

        servo_write(0, 90);
        servo_write(1, 145);
        vTaskDelay(pdMS_TO_TICKS(2000));

        servo_write(1, 90);
        servo_write(2, 50);
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}

