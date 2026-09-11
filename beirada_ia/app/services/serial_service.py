"""
Serviço de comunicação serial USB com o ESP32-S3.

Protocolo: envia uma linha ASCII "N\n" por peça, onde N é a classe (1..3).
A escrita é serializada por lock e com intervalo mínimo entre envios
para não saturar a porta nem o parser do firmware.
"""
import os
import threading
from time import monotonic
from typing import Optional

import serial  # pyserial

from services.log_service import log_event


# ─────────────────────────────────────────────────────────────────────────
# Configuração (sobrescreva via variáveis de ambiente)
# ─────────────────────────────────────────────────────────────────────────
SERIAL_PORT = os.getenv("ESP32_SERIAL_PORT", "/dev/ttyACM0")
SERIAL_BAUD = int(os.getenv("ESP32_SERIAL_BAUD", "115200"))
MIN_INTERVAL_S = float(os.getenv("ESP32_MIN_INTERVAL_S", "0.1"))  # 100 ms
SERIAL_ENABLED = os.getenv("ESP32_SERIAL_ENABLED", "true").lower() == "true"


# ─────────────────────────────────────────────────────────────────────────
# Estado interno
# ─────────────────────────────────────────────────────────────────────────
_lock = threading.Lock()
_port: Optional[serial.Serial] = None
_last_send_time: float = 0.0


def _ensure_open() -> Optional[serial.Serial]:
    """Abre a porta serial na primeira chamada. Retorna None em falha."""
    global _port
    if _port is not None and _port.is_open:
        return _port
    try:
        _port = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=0.1)
        log_event(
            "serial_opened",
            port=SERIAL_PORT,
            baud=SERIAL_BAUD,
        )
        return _port
    except Exception as e:
        log_event(
            "serial_open_error",
            level="ERROR",
            port=SERIAL_PORT,
            reason=str(e),
        )
        _port = None
        return None


def enviar_classe(classe: int, forcar: bool = False) -> bool:
    """
    Envia uma classe para o ESP32 via serial.

    Args:
        classe: valor inteiro (0..9). O firmware aceita 1..3.
        forcar: se True, ignora o intervalo mínimo entre envios.

    Returns:
        True se a escrita foi bem-sucedida, False caso contrário.
    """
    global _last_send_time

    if not SERIAL_ENABLED:
        return False

    if not isinstance(classe, int) or not (0 <= classe <= 9):
        log_event(
            "serial_invalid_class",
            level="WARN",
            classe=classe,
        )
        return False

    agora = monotonic()
    if not forcar and (agora - _last_send_time) < MIN_INTERVAL_S:
        # Evita flood: ignora envios muito próximos
        return False

    with _lock:
        ser = _ensure_open()
        if ser is None:
            return False

        try:
            payload = f"{classe}\n".encode("ascii")
            ser.write(payload)
            _last_send_time = agora
            return True
        except Exception as e:
            log_event(
                "serial_write_error",
                level="ERROR",
                classe=classe,
                reason=str(e),
            )
            # Tenta reabrir na próxima chamada
            global _port
            try:
                if _port is not None:
                    _port.close()
            except Exception:
                pass
            _port = None
            return False


def fechar_porta() -> None:
    """Fecha a porta serial (útil em shutdown)."""
    global _port
    with _lock:
        if _port is not None:
            try:
                _port.close()
            except Exception:
                pass
            _port = None
            log_event("serial_closed", port=SERIAL_PORT)