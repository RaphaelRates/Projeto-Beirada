#ifndef SERIAL_H
#define SERIAL_H

#include "esp_err.h"

// Inicializa o driver UART/USB e dispara a task de leitura
esp_err_t serial_init(void);

#endif // SERIAL_H