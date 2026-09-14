idf_component_register(SRCS "serial.c" "servo.c" "ledc_basic_example_main.c" "filas.c"
                    PRIV_REQUIRES esp_driver_ledc esp_driver_gpio esp_driver_uart
                    INCLUDE_DIRS ".")
