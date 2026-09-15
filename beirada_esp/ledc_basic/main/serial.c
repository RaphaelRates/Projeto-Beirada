#include "serial.h"
#include "filas.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdlib.h>
#include <string.h>

static const char *TAG = "UART_COMUNICAO";

// UART_NUM_0 é mapeado diretamente para a porta USB/Serial padrão do ESP32-S3
#define UART_PORT_NUM      UART_NUM_0
#define UART_BAUD_RATE     115200
#define BUF_SIZE           128

static void uart_rx_task(void *pvParameters)
{
    uint8_t *data = (uint8_t *) malloc(BUF_SIZE);
    char buffer[16];
    int buf_idx = 0;

    ESP_LOGI(TAG, "Task de leitura Serial/USB iniciada. Aguardando dados do RPi 5...");

    while (1) {
        // Lê os bytes que chegaram na porta serial (bloqueante com timeout de 300ms)
        int len = uart_read_bytes(UART_PORT_NUM, data, BUF_SIZE - 1, pdMS_TO_TICKS(300));

        if (len > 0) {
            for (int i = 0; i < len; i++) {
                char c = (char)data[i];

                // Quando encontra a quebra de linha '\n' ou '\r', processa o comando completo
                if (c == '\n' || c == '\r') {
                    if (buf_idx > 0) {
                        buffer[buf_idx] = '\0'; // Finaliza a string

                        // Converte o texto recebido para inteiro (ex: "1", "2", "3", "4")
                        uint8_t classe_recebida = (uint8_t)atoi(buffer);

                        ESP_LOGI(TAG, "Comando serial recebido: '%s' -> Classe: %d", buffer, classe_recebida);

                        // Injeta a classe diretamente no pipeline de filas e sensores
                        peca_para_fila(classe_recebida);

                        // Reseta o índice do buffer para a próxima mensagem
                        buf_idx = 0;
                        
                    }
                } else if (buf_idx < (sizeof(buffer) - 1)) {
                    // Acumula os caracteres imprimíveis no buffer
                    if (c >= '0' && c <= '9') {
                        buffer[buf_idx++] = c;
                    }
                }
            }
        }
    }

    free(data);
    vTaskDelete(NULL);
}

esp_err_t serial_init(void)
{
    uart_config_t uart_config = {
        .baud_rate = UART_BAUD_RATE,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    // Configura os parâmetros da UART
    esp_err_t err = uart_param_config(UART_PORT_NUM, &uart_config);
    if (err != ESP_OK) return err;

    // Instala o driver UART utilizando os pinos padrão de TX/RX do console
    err = uart_driver_install(UART_PORT_NUM, BUF_SIZE * 2, 0, 0, NULL, 0);
    if (err != ESP_OK) return err;

    // Cria a task com prioridade adequada para processar a serial em tempo real
    xTaskCreate(
        uart_rx_task,
        "uart_rx_task",
        3072,
        NULL,
        10, // Prioridade alta para não perder bytes
        NULL
    );

    ESP_LOGI(TAG, "Driver UART configurado com sucesso a 115200 baud.");
    return ESP_OK;
}