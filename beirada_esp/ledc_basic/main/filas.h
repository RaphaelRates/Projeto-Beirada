#ifndef FILAS_H
#define FILAS_H

#include <stdint.h>
#include "esp_err.h"

// Inicializa as filas e dispara as worker tasks de cada servo
esp_err_t logica_filas_init(void);

// Encaminha a classe do objeto detectado para a fila correspondente
void peca_para_fila(uint8_t piece_class);

#endif // FILAS_H