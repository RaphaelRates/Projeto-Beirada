import os
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
import json


class GrafanaCloudExporter:
    """Exportador opcional para Grafana Cloud usando o endpoint remote_write.

    Envia uma série de contagem por segundo de objetos detectados de forma
    compatível com o Prometheus/Grafana. Para evitar contagem duplicada do
    tracking YOLO, a métrica deve refletir deteções únicas por janela e não
    a soma de boxes repetidos cruzando frames.
    """

    def __init__(self,
                 endpoint: str | None = None,
                 username: str | None = None,
                 password: str | None = None,
                 enabled: bool = False,
                 push_interval_sec: float = 1.0):
        self.endpoint = endpoint or os.getenv("GRAFANA_REMOTE_WRITE_ENDPOINT")
        self.username = username or os.getenv("GRAFANA_USERNAME")
        self.password = password or os.getenv("GRAFANA_PASSWORD")
        self.enabled = enabled or bool(self.endpoint)
        self.push_interval_sec = push_interval_sec
        self._lock = threading.Lock()
        self._last_push = 0.0
        self._samples = []

    def build_payload(self, objects_per_second: float,
                      model_name: str = "yolov8n_v3.pt",
                      source: str = "api",
                      tracking: str = "track-aware") -> dict:
        """Constrói o payload do remote write em formato Prometheus-compatible.

        Labels do tipo __name__ são usados porque o Grafana Cloud / Mimir
        aceita o nome da métrica no payload do remote-write.
        """
        ts = int(time.time() * 1000)
        return {
            "timeseries": [
                {
                    "labels": {
                        "__name__": "beirada_objects_detected_per_second",
                        "model": model_name,
                        "source": source,
                        "tracking": tracking,
                    },
                    "samples": [
                        {
                            "timestamp": ts,
                            "value": float(objects_per_second),
                        }
                    ],
                }
            ]
        }

    def push_count(self, objects_per_second: float,
                   model_name: str = "yolov8n_v3.pt",
                   source: str = "api",
                   tracking: str = "track-aware") -> bool:
        """Envia uma amostra por segundo para Grafana Cloud.

        Observação: a função evita enviar duas amostras na mesma janela;
        se o intervalo de pull estiver baixo, o push é agrupado por lock.
        """
        if not self.enabled or not self.endpoint:
            return False

        now = time.time()
        with self._lock:
            if now - self._last_push < self.push_interval_sec:
                return False
            self._last_push = now

        payload = self.build_payload(objects_per_second, model_name, source, tracking)
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(self.endpoint,
                                     data=data,
                                     method="POST",
                                     headers={
                                         "Content-Type": "application/json",
                                         "User-Agent": "beirada-grafana-exporter/1.0",
                                     })

        if self.username and self.password:
            import base64
            raw = f"{self.username}:{self.password}".encode("utf-8")
            req.add_header("Authorization", "Basic " + base64.b64encode(raw).decode("utf-8"))

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status in (200, 202)
        except Exception:
            return False


if __name__ == "__main__":
    exp = GrafanaCloudExporter(enabled=False)
