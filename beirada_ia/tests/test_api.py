"""
tests/test_api.py
Cobertura: smoke test, unit tests e integration test da YOLO Inference API.
Pré-requisito: models/yolov8n.pt presente no sistema de arquivos.
"""
import base64
import importlib
import inspect
import io
import json
import os

# Ajusta o PYTHONPATH: raiz do projeto (para "app" ser pacote) e app/ (para os imports internos de main.py, como "from schemas import ...")
import sys
import threading
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, UnidentifiedImageError


class GrafanaCloudExporter:
    def __init__(self, endpoint=None, username=None, password=None, enabled=True):
        self.endpoint = endpoint
        self.username = username
        self.password = password
        self.enabled = enabled

    def build_payload(self, value, model_name=None, source=None, tracking=None):
        return {
            "timeseries": [
                {
                    "labels": {
                        "__name__": "beirada_objects_detected_per_second",
                        "model_name": model_name or "unknown",
                        "source": source or "unknown",
                        "tracking": tracking or "unknown",
                    },
                    "samples": [{"value": value}],
                }
            ]
        }

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))


os.environ.setdefault("MODEL_NAME", "yolov8n.pt")


from model import get_default_model_name
from preprocessing.preprocessor import CONFIG_DEFAULT
from schemas import PredictRequest

from app import _decode_image, _run_stream_or_camera_only, app, stream_camera

try:
    from app import OptimizedCamera, RealtimeDetector
except Exception:
    OptimizedCamera = None
    RealtimeDetector = None

client = TestClient(app)


def test_metrics_ensure_file_creates_default_file_without_recursing(tmp_path, monkeypatch):
    """Regression test for the metrics helper: the file should be initialized
    once from the default payload instead of mutually calling save/ensure.
    """
    app_module = importlib.import_module("app")
    metrics_file = tmp_path / "beirada_metrics.json"
    metrics_lock = tmp_path / "beirada_metrics.lock"
    monkeypatch.setattr(app_module, "_metrics_file", metrics_file)
    monkeypatch.setattr(app_module, "_metrics_lock_file", metrics_lock)

    app_module._metrics_ensure_file()

    assert metrics_file.exists()
    assert json.loads(metrics_file.read_text(encoding="utf-8")) == {
        "total": 0,
        "success": 0,
        "total_ms": 0.0,
    }


def test_publish_detection_metrics_filters_to_supported_project_classes():
    app_module = importlib.import_module("app")

    class FakeModel:
        names: ClassVar[list[str]] = ["serrote", "martelo", "parafuso", "estilete", "caminhao"]

    class FakeBox:
        def __init__(self, cls_id, confidence):
            self.cls = [type("C", (), {"__getitem__": lambda self, _: cls_id})()]
            self.conf = [type("C", (), {"__getitem__": lambda self, _: confidence})()]

    class FakeResult:
        def __init__(self, boxes):
            self.boxes = boxes

    fake_results = [
        FakeResult([
            FakeBox(0, 0.90),
            FakeBox(1, 0.81),
            FakeBox(4, 0.75),
        ])
    ]

    summary = app_module._publish_detection_metrics(FakeModel(), fake_results)

    assert summary == [
        {"class": "serrote", "confidence": 0.9},
        {"class": "martelo", "confidence": 0.81},
    ]


def test_default_api_confidence_and_preprocess_infer_size():
    assert PredictRequest().confidence == 0.65
    assert CONFIG_DEFAULT.infer_size == 240


def test_stream_camera_route_supports_stream_optimization_params():
    params = inspect.signature(stream_camera).parameters
    assert "infer_every" in params
    assert "jpeg_quality" in params


def test_stream_camera_route_exposes_optimized_stream_classes():
    assert OptimizedCamera is not None
    assert RealtimeDetector is not None


def test_optimized_camera_read_returns_latest_frame_from_latest_slot():
    assert OptimizedCamera is not None
    camera = OptimizedCamera.__new__(OptimizedCamera)
    camera._latest_frame = np.zeros((4, 4, 3), dtype=np.uint8)
    camera._latest_lock = threading.Lock()
    camera.frames_out = 0

    latest = camera.read(timeout=0.01)
    assert latest is camera._latest_frame


ASSETS = Path(__file__).parent / "assets"




# ────────────────────────────────────────────────────────────
# SMOKE TEST — o serviço responde?
# ────────────────────────────────────────────────────────────


class TestSmoke:
    def test_health_status_200(self):
        """API deve retornar HTTP 200 com status ok."""
        resp = client.get("/health")
        assert resp.status_code == 200


    def test_health_payload_structure(self):
        """Payload deve conter status, model_loaded e model_name."""
        data = client.get("/health").json()
        assert "status" in data
        assert "model_loaded" in data
        assert "model_name" in data


    def test_metrics_endpoint_accessible(self):
        """Endpoint /metrics deve estar acessível."""
        resp = client.get("/metrics")
        assert resp.status_code == 200


    def test_metrics_endpoint_returns_active_model_name(self):
        """Endpoint /metrics deve refletir o modelo ativo em tempo real."""
        resp = client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "model_name" in data
        assert data["model_name"] == get_default_model_name()




# ────────────────────────────────────────────────────────────
# UNIT TESTS — funções isoladas
# ────────────────────────────────────────────────────────────


class TestDecodeImage:
    def _make_b64_image(self, width=32, height=32, fmt="JPEG"):
        img = Image.new("RGB", (width, height), color=(128, 64, 192))
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return base64.b64encode(buf.getvalue()).decode()


    def test_returns_numpy_array(self):
        result = _decode_image(self._make_b64_image())
        assert isinstance(result, np.ndarray)


    def test_correct_shape(self):
        result = _decode_image(self._make_b64_image(64, 48))
        assert result.shape == (48, 64, 3)


    def test_png_format(self):
        result = _decode_image(self._make_b64_image(fmt="PNG"))
        assert result.shape[2] == 3


    def test_invalid_base64_raises(self):
        with pytest.raises(UnidentifiedImageError):
            _decode_image("dado_invalido_nao_e_base64")




# ────────────────────────────────────────────────────────────
# INTEGRATION TESTS — fluxo completo de inferência
# ────────────────────────────────────────────────────────────


def test_run_stream_or_camera_only_returns_frame_when_model_is_missing():
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    result = _run_stream_or_camera_only(frame, None, 0.60)
    assert result is frame


def test_grafana_exporter_builds_prometheus_remote_write_payload():
    exporter = GrafanaCloudExporter(endpoint="https://prometheus.example/api/prom/push",
                                     username="u",
                                     password="p",
                                     enabled=True)
    payload = exporter.build_payload(3.0, model_name="yolov8n_v3.pt", source="api", tracking="track-aware")
    assert payload["timeseries"][0]["labels"]["__name__"] == "beirada_objects_detected_per_second"
    assert payload["timeseries"][0]["samples"][0]["value"] == 3.0


class TestPredictEndpoint:
    @pytest.fixture
    def zidane_b64(self):
        img_path = ASSETS / "zidane.jpg"
        return base64.b64encode(img_path.read_bytes()).decode()


    def test_predict_returns_200(self, zidane_b64):
        resp = client.post("/predict", json={
            "image_base64": zidane_b64,
            "confidence": 0.3,
        })
        assert resp.status_code == 200


    def test_predict_detects_at_least_one_object(self, zidane_b64):
        """A imagem zidane.jpg deve produzir ao menos 1 detecção com conf >= 0.3."""
        data = client.post("/predict", json={
            "image_base64": zidane_b64,
            "confidence": 0.3,
        }).json()
        assert len(data["detections"]) >= 1


    def test_predict_response_schema(self, zidane_b64):
        """Resposta deve conter todos os campos do schema PredictResponse."""
        data = client.post("/predict", json={
            "image_base64": zidane_b64,
            "confidence": 0.3,
        }).json()
        assert "detections" in data
        assert "inference_ms" in data
        assert "model_used" in data
        assert "image_width" in data
        assert "image_height" in data
        assert data["inference_ms"] > 0


    def test_predict_detection_fields(self, zidane_b64):
        """Cada detecção deve ter label, confidence e bbox válidos."""
        data = client.post("/predict", json={
            "image_base64": zidane_b64,
            "confidence": 0.3,
        }).json()
        for det in data["detections"]:
            assert isinstance(det["label"], str)
            assert 0.0 <= det["confidence"] <= 1.0
            assert len(det["bbox"]) == 4


    def test_predict_missing_input_returns_422(self):
        """Requisição sem imagem deve retornar HTTP 422."""
        resp = client.post("/predict", json={
            "confidence": 0.3
        })
        assert resp.status_code == 422




# ────────────────────────────────────────────────────────────
# BATCH ENDPOINT
# ────────────────────────────────────────────────────────────


class TestBatchEndpoint:
    @pytest.fixture
    def two_images_b64(self):
        img_path = ASSETS / "zidane.jpg"
        b64 = base64.b64encode(img_path.read_bytes()).decode()
        return [b64, b64]   # mesma imagem duas vezes para simplificar


    def test_batch_returns_correct_count(self, two_images_b64):
        data = client.post("/predict/batch", json={
            "images_base64": two_images_b64,
            "confidence": 0.3,
        }).json()
        assert len(data["results"]) == 2


    def test_batch_total_ms_is_positive(self, two_images_b64):
        data = client.post("/predict/batch", json={
            "images_base64": two_images_b64,
            "confidence": 0.3,
        }).json()
        assert data["total_inference_ms"] > 0