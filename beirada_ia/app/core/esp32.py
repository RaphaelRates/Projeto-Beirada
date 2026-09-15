# esp32.py
import serial
import threading
import time

_ser = None
_lock = threading.Lock()

def iniciar(porta="/dev/ttyUSB0", baud=115200):
    """Abre a porta serial uma vez. Chame no início do programa."""
    global _ser
    try:
        _ser = serial.Serial(porta, baud, timeout=0.1)
        time.sleep(2)   # aguarda ESP32 bootar após abrir a porta
        print(f"[ESP32] Conectado em {porta} @ {baud}")
        enviar("conectado")
    except serial.SerialException as e:
        _ser = None
        print(f"[ESP32] Falha ao abrir {porta}: {e}")

def enviar(msg: str):
    """Envia uma string + '\\n' para o ESP32. Não bloqueia se a serial cair."""
    if _ser is None or not _ser.is_open:
        return
    try:
        with _lock:   # evita escrita concorrente entre threads
            _ser.write((msg + "\n").encode("utf-8"))
    except serial.SerialException as e:
        print(f"[ESP32] Erro ao enviar: {e}")

def fechar():
    global _ser
    if _ser and _ser.is_open:
        _ser.close()