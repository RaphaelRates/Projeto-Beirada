import os
import time
from collections import defaultdict


class TrackAwareCounter:
    """Contador de objetos por segundo com cuidado de tracking.

    O objetivo é evitar que o mesmo objeto detectado em vários frames
    produza contagens infladas. Em vez de somar boxes de cada frame, a
    lógica usa a janela de tempo e mantém uma lista de objetos vistos por
    segundo para normalizar contagens de deteções. Isso é compatível com
    o padrão de `track_id` do YOLO quando houver tracking.
    """

    def __init__(self, window_seconds: float = 1.0):
        self.window_seconds = window_seconds
        self._seen = defaultdict(float)
        self._lock = None

    def update(self, detections: list[dict], frame_time: float | None = None,
               track_ids: list[str] | None = None) -> float:
        """Retorna objetos detectados por segundo usando uma janela de tempo.

        Cada saída é uma estimativa de objetos por segundo, construída a
        partir de deteções únicas observadas na janela atual.
        """
        now = frame_time if frame_time is not None else time.time()
        # limpe registros fora da janela
        expire_before = now - self.window_seconds
        for key in list(self._seen.keys()):
            if self._seen[key] < expire_before:
                del self._seen[key]

        # uso do `track_id` quando existir, do contrário a chave pelo label/conf
        uniques = set()
        for det in detections:
            label = str(det.get("label", "unknown"))
            conf = float(det.get("confidence", 0.0))
            track_id = str(det.get("track_id") or det.get("id") or "")
            if track_id:
                key = f"track::{track_id}"
            else:
                key = f"label::{label}::{conf}::{id(det)}"
            uniques.add(key)

        # adota a contagem de objetos únicos no período
        for key in uniques:
            self._seen[key] = now

        # contagem normalizada por segundo.
        current_count = len(self._seen)
        return current_count / self.window_seconds


if __name__ == "__main__":
    counter = TrackAwareCounter()
    print(counter.update([
        {"label": "person", "confidence": 0.7, "track_id": "a"},
    ]))
