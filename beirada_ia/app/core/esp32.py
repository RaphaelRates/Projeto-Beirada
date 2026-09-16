# esp32.py
import threading
import time

import serial

_ser = None
_lock = threading.Lock()
_monitor_thread = None
_stop_monitor = threading.Event()
_porta = "/dev/ttyUSB0"
_baud = 115200
_INTERVALO_VERIFICACAO = 3

def iniciar(porta="/dev/ttyUSB0", baud=115200):
    """Inicia a conexão e monitora o ESP32 continuamente."""
    global _monitor_thread, _porta, _baud
    _porta = porta
    _baud = baud
    _stop_monitor.clear()

    _tentar_conectar()

    if _monitor_thread is None or not _monitor_thread.is_alive():
        _monitor_thread = threading.Thread(
            target=_monitorar_conexao,
            name="esp32-connection-monitor",
            daemon=True,
        )
        _monitor_thread.start()


def _tentar_conectar():
    global _ser
    try:
        with _lock:
            if _ser is not None and _ser.is_open:
                print("[ESP32] Conexão verificada.")
                return True

            _ser = serial.Serial(_porta, _baud, timeout=0.1)

        time.sleep(2)   # aguarda ESP32 bootar após abrir a porta
        print(f"[ESP32] Conectado em {_porta} @ {_baud}")
        enviar("80")
        return True
    except (serial.SerialException, OSError) as e:
        with _lock:
            _ser = None
        print(f"[ESP32] Sem conexão. Nova tentativa em {_INTERVALO_VERIFICACAO}s: {e}")
        return False


def _monitorar_conexao():
    while not _stop_monitor.wait(_INTERVALO_VERIFICACAO):
        _tentar_conectar()

def enviar(msg: str):
    """Envia uma string + '\\n' para o ESP32. Não bloqueia se a serial cair."""
    global _ser
    try:
        with _lock:   # evita escrita concorrente entre threads
            if _ser is None or not _ser.is_open:
                return
            _ser.write((msg + "\n").encode("utf-8"))
    except (serial.SerialException, OSError) as e:
        print(f"[ESP32] Erro ao enviar: {e}")
        with _lock:
            _ser = None

def fechar():
    global _ser
    _stop_monitor.set()
    with _lock:
        if _ser and _ser.is_open:
            _ser.close()
        _ser = None