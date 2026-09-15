import asyncio
import base64
import fcntl
import io
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import cv2
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx
import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from model import get_default_model_name, load_model
from PIL import Image
from prometheus_client import Counter, Gauge, start_http_server
from schemas import (
    BatchPredictRequest,
    BatchPredictResponse,
    Detection,
    HealthResponse,
    MetricsResponse,
    PredictRequest,
    PredictResponse,
)

from preprocessing.preprocessor import CONFIG_DEFAULT, Preprocessor
from grafana_exporter import GrafanaCloudExporter
from grafana_tracking import TrackAwareCounter

templates = Jinja2Templates(directory="templates")

try:
    _METRICS_PORT = int(os.environ.get("PROMETHEUS_PORT", "8001"))
    start_http_server(_METRICS_PORT)
except Exception:
    pass

INFERENCE_TIME = Gauge(
    "yolo_inference_time_seconds",
    "Tempo de inferência do YOLO em segundos (última execução)",
)
DETECTIONS_COUNT = Gauge(
    "yolo_detections_count",
    "Número de objetos detectados na última inferência",
)
DETECTIONS_TOTAL = Counter(
    "yolo_detections_total",
    "Total cumulativo de objetos detectados pelo YOLO",
)
DETECTIONS_BY_CLASS = Counter(
    "yolo_detections_by_class_total",
    "Total cumulativo de objetos detectados pelo YOLO por classe",
    ["class_name"],
)
DETECTION_CONFIDENCE = Gauge(
    "yolo_detection_confidence_last",
    "Última confiança por classe observada na última inferência",
    ["class_name"],
)
STREAM_ACTIVE = Gauge(
    "yolo_stream_active",
    "1 se há um stream de câmera em andamento, 0 caso contrário",
)
STREAM_FPS = Gauge(
    "yolo_stream_fps",
    "Taxa de quadros por segundo entregues pelo stream (média móvel simples)",
)

_MONITORED_CLASSES = {
    "serrote",
    "martelo",
    "parafuso",
    "estilete",
}


app = FastAPI(
    title="YOLO Inference API",
    description="API REST para inferência com YOLOv8 e Câmera no Raspberry Pi 5",
    version="1.1.0",
)

_metrics = {"total": 0, "success": 0, "total_ms": 0.0}
_metrics_file = Path("/tmp/beirada_metrics.json")
_metrics_lock_file = Path("/tmp/beirada_metrics.lock")
_streaming_lock = asyncio.Lock()


def _metrics_default():
    return {"total": 0, "success": 0, "total_ms": 0.0}


def _metrics_ensure_file():
    _metrics_file.parent.mkdir(parents=True, exist_ok=True)
    if not _metrics_file.exists():
        with _metrics_file.open("w", encoding="utf-8") as fp:
            json.dump(_metrics_default(), fp)


def _metrics_load():
    _metrics_ensure_file()
    try:
        with _metrics_file.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        merged = _metrics_default()
        merged.update(data)
        return merged
    except Exception:
        return _metrics_default()


def _metrics_save(metrics):
    _metrics_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = _metrics_file.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(metrics, fp)
    os.replace(str(tmp), str(_metrics_file))


def _metrics_update(total_delta: int = 0, success_delta: int = 0, total_ms_delta: float = 0.0):
    try:
        _metrics_ensure_file()
        with _metrics_lock_file.open("a+") as lock_fp:
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
            metrics = _metrics_load()
            metrics["total"] += int(total_delta)
            metrics["success"] += int(success_delta)
            metrics["total_ms"] += float(total_ms_delta)
            _metrics.update(metrics)
            _metrics_save(metrics)
    except Exception:
        metrics = _metrics.copy()
        metrics["total"] += int(total_delta)
        metrics["success"] += int(success_delta)
        metrics["total_ms"] += float(total_ms_delta)
        _metrics.update(metrics)


def _metrics_read_for_response():
    metrics = _metrics_load()
    _metrics.update(metrics)
    return metrics


def log_event(event: str, level: str = "INFO", **kwargs):
    """Emite um evento estruturado em JSON para stdout."""
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "level": level,
        "event": event,
        **kwargs,
    }
    print(json.dumps(record, ensure_ascii=False), flush=True)


def _publish_detection_metrics(model, results):
    """Publica para Prometheus/Grafana apenas as quatro classes de interesse
    do projeto: serrote, martelo, parafuso e estilete. As restantes são
    filtradas do array de observabilidade e não alteram os counters/gauges.
    """
    summary = []
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0].item())
            conf_val = float(box.conf[0].item())
            cls_name = model.names[cls_id]
            cls_name_lower = cls_name.lower()

            if cls_name_lower not in _MONITORED_CLASSES:
                continue

            DETECTIONS_BY_CLASS.labels(cls_name).inc()
            DETECTION_CONFIDENCE.labels(cls_name).set(conf_val)
            summary.append({"class": cls_name, "confidence": round(conf_val, 4)})
    return summary


_preprocessor = Preprocessor(CONFIG_DEFAULT)  # instância global


def _run_inference(image_np: np.ndarray, model_name: str, confidence: float) -> PredictResponse:
    """Roda a inferência com pré-processamento e atualiza as métricas Prometheus.
    Observação: antes havia duas funções `_run_inference` no arquivo — a segunda
    sobrescrevia a primeira, então o pré-processamento (letterbox + ajuste de
    bbox) nunca era realmente executado nos endpoints /predict*. Esta versão
    unifica as duas: mantém o pré-processamento E a atualização de métricas.
    """
    model = load_model(model_name)

    frame_bgr = image_np[:, :, ::-1]
    preproc_res = _preprocessor.process(frame_bgr)
    frame_ready = preproc_res.frame  # RGB, letterboxed

    t0 = time.perf_counter()
    results = model(frame_ready, conf=confidence, verbose=False)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    
    total_detections = sum(len(r.boxes) for r in results)
    INFERENCE_TIME.set(elapsed_ms / 1000)
    DETECTIONS_COUNT.set(total_detections)
    DETECTIONS_TOTAL.inc(total_detections)

    _publish_detection_metrics(model, results)

    detections = []
    for r in results:
        for box in r.boxes:

            bbox_lb = box.xyxy[0].numpy().reshape(1, 4)
            bbox_orig = _preprocessor.adjust_boxes(bbox_lb, preproc_res)[0]
            cls_id = int(box.cls[0].item())
            conf_val = float(box.conf[0].item())

            detections.append(Detection(
                label=model.names[cls_id],
                confidence=round(conf_val, 4),
                bbox=[round(float(c), 2) for c in bbox_orig],
            ))

    h, w = image_np.shape[:2]
    return PredictResponse(
        detections=detections,
        inference_ms=round(elapsed_ms, 2),
        model_used=model_name,
        image_width=w,
        image_height=h,
    )


def _run_stream_or_camera_only(frame: np.ndarray, model, confidence: float):
    """Roda a inferência YOLO em um frame de streaming e atualiza as métricas
    Prometheus em tempo real, para que o Grafana reflita o stream ao vivo.

    Fallback: se o modelo não puder rodar, devolve o frame bruto da câmera e
    marca o erro no contador `yolo_stream_inference_errors_total`. Isso mantém
    o stream vivo mesmo quando o modelo está offline ou indisponível.
    """
    if model is None:
        return frame

    try:
        t0 = time.perf_counter()
        results = model.predict(
            source=frame,
            conf=confidence,
            imgsz=300,
            verbose=False,
            half=True,
            iou=0.15,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        total_detections = sum(len(r.boxes) for r in results)
        INFERENCE_TIME.set(elapsed_ms / 1000)
        DETECTIONS_COUNT.set(total_detections)
        DETECTIONS_TOTAL.inc(total_detections)

        return results[0].plot()
    except Exception as exc:
        log_event("stream_yolo_fallback_camera_only",level="WARN",reason=str(exc),confidence=confidence,)
        return frame


def _decode_image(image_base64: str) -> np.ndarray:
    raw = base64.b64decode(image_base64)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    return np.array(img)


def _load_image_from_request(request: PredictRequest) -> np.ndarray:
    if not request.image_base64 and not request.image_url:
        raise HTTPException(status_code=422, detail="Forneça image_base64 ou image_url.")

    if request.image_base64:
        return _decode_image(request.image_base64)

    try:
        resp = httpx.get(request.image_url,timeout=15.0,follow_redirects=True,)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        return np.array(img)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"Erro ao baixar imagem: {e}") from e


def _capture_frame_from_camera(device_id: int = 0) -> np.ndarray:
    """Captura frame via rpicam-still/libcamera-still ou OpenCV."""
    for cmd_tool in ["rpicam-still", "libcamera-still"]:
        try:
            cmd = [
                cmd_tool,
                "-t", "500",
                "-n",
                "-o", "-",
                "--width", "1300",
                "--height", "720",
                "-e", "jpg",
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout:
                img = Image.open(io.BytesIO(result.stdout)).convert("RGB")
                return np.array(img)
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            continue

    cap = cv2.VideoCapture(device_id)
    if cap.isOpened():
        try:
            for _ in range(3):
                cap.read()
            ret, frame_bgr = cap.read()
            if ret and frame_bgr is not None:
                return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        finally:
            cap.release()

    raise HTTPException(
        status_code=500,
        detail="Falha ao capturar imagem da câmera. Verifique a conexão do cabo flat.",
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    model_name = get_default_model_name()
    try:
        load_model(model_name)
        loaded = True
    except Exception as e:
        loaded = False
        log_event("health_error", level="ERROR", reason=str(e))

    return HealthResponse(
        status="ok",
        model_loaded=loaded,
        model_name=model_name,
    )


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    request_id = str(uuid.uuid4())[:8]
    _metrics_update(total_delta=1)

    log_event(
        "predict_start",
        request_id=request_id,
        model=request.model_name,
        confidence=request.confidence,
    )

    if not request.image_base64 and not request.image_url:
        log_event(
            "predict_error",
            level="WARN",
            request_id=request_id,
            reason="missing_input",
        )
        raise HTTPException(
            status_code=422,
            detail="Forneça image_base64 ou image_url.",
        )

    try:
        img = _load_image_from_request(request)
        result = _run_inference(
            img,
            request.model_name,
            request.confidence,
        )

        _metrics_update(success_delta=1, total_ms_delta=result.inference_ms)

        log_event(
            "predict_complete",
            request_id=request_id,
            model=result.model_used,
            detections=len(result.detections),
            inference_ms=result.inference_ms,
            image_size=f"{result.image_width}x{result.image_height}",
        )
        return result

    except HTTPException:
        raise
    except FileNotFoundError as e:
        log_event(
            "predict_error",
            level="ERROR",
            request_id=request_id,
            reason=str(e),
        )
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        log_event(
            "predict_error",
            level="ERROR",
            request_id=request_id,
            reason=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/predict/image", responses={200: {"content": {"image/jpeg": {}}}})
def predict_image(request: PredictRequest):
    """Executa inferência em imagem enviada e retorna JPEG com caixas delimitadoras."""
    request_id = str(uuid.uuid4())[:8]
    _metrics_update(total_delta=1)

    log_event(
        "predict_image_start",
        request_id=request_id,
        model=request.model_name,
        confidence=request.confidence,
    )

    try:
        img_rgb = _load_image_from_request(request)
        model = load_model(request.model_name)

        t0 = time.perf_counter()
        results = model(img_rgb, conf=request.confidence, verbose=False)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        total_detections = sum(len(r.boxes) for r in results)
        INFERENCE_TIME.set(elapsed_ms / 1000)
        DETECTIONS_COUNT.set(total_detections)
        DETECTIONS_TOTAL.inc(total_detections)

        classes_confidence_array = _publish_detection_metrics(model, results)
        log_event(
            "predict_image_detections",
            request_id=request_id,
            model=request.model_name,
            detections=classes_confidence_array,
        )

        _metrics_update(success_delta=1, total_ms_delta=elapsed_ms)

        annotated_array = results[0].plot()
        annotated_pil = Image.fromarray(annotated_array)

        buffer = io.BytesIO()
        annotated_pil.save(buffer, format="JPEG", quality=95)

        log_event(
            "predict_image_complete",
            request_id=request_id,
            inference_ms=round(elapsed_ms, 2),
        )

        return Response(content=buffer.getvalue(), media_type="image/jpeg")

    except HTTPException:
        raise
    except FileNotFoundError as e:
        log_event(
            "predict_image_error",
            level="ERROR",
            request_id=request_id,
            reason=str(e),
        )
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        log_event(
            "predict_image_error",
            level="ERROR",
            request_id=request_id,
            reason=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/predict/camera", response_model=PredictResponse)
def predict_from_camera(
    device_id: int = Query(0, description="Índice do dispositivo (/dev/videoX)"),
    confidence: float = Query(0.65, ge=0.0, le=1.0, description="Limiar de confiança"),
    model_name: str = Query("yolov8n_v4.pt", description="Modelo YOLO a ser utilizado"),
):
    """Captura uma foto pela câmera, executa inferência e retorna as detecções."""
    request_id = str(uuid.uuid4())[:8]
    _metrics_update(total_delta=1)

    log_event(
        "camera_predict_start",
        request_id=request_id,
        device_id=device_id,
        model=model_name,
        confidence=confidence,
    )

    try:
        img_rgb = _capture_frame_from_camera(device_id=device_id)
        result = _run_inference(img_rgb, model_name, confidence)

        _metrics_update(success_delta=1, total_ms_delta=result.inference_ms)

        log_event(
            "camera_predict_complete",
            request_id=request_id,
            detections=len(result.detections),
            inference_ms=result.inference_ms,
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        log_event(
            "camera_predict_error",
            level="ERROR",
            request_id=request_id,
            reason=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/predict/camera/image", responses={200: {"content": {"image/jpeg": {}}}})
def predict_from_camera_image(
    device_id: int = Query(0, description="Índice do dispositivo (/dev/videoX)"),
    confidence: float = Query(0.65, ge=0.0, le=1.0, description="Limiar de confiança"),
    model_name: str = Query("yolov8n_v4.pt", description="Modelo YOLO a ser utilizado"),
):
    """Captura imagem da câmera, executa inferência e retorna JPEG anotado."""
    request_id = str(uuid.uuid4())[:8]
    _metrics_update(total_delta=1)

    log_event(
        "camera_image_start",
        request_id=request_id,
        device_id=device_id,
        model=model_name,
        confidence=confidence,
    )

    try:
        img_rgb = _capture_frame_from_camera(device_id=device_id)
        model = load_model(model_name)

        t0 = time.perf_counter()
        results = model(img_rgb, conf=confidence, verbose=False)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        total_detections = sum(len(r.boxes) for r in results)
        INFERENCE_TIME.set(elapsed_ms / 1000)
        DETECTIONS_COUNT.set(total_detections)
        DETECTIONS_TOTAL.inc(total_detections)

        classes_confidence_array = _publish_detection_metrics(model, results)
        log_event(
            "camera_image_detections",
            request_id=request_id,
            model=model_name,
            detections=classes_confidence_array,
        )

        _metrics_update(success_delta=1, total_ms_delta=elapsed_ms)

        annotated_array = results[0].plot()
        annotated_pil = Image.fromarray(annotated_array)

        buffer = io.BytesIO()
        annotated_pil.save(buffer, format="JPEG", quality=95)

        log_event(
            "camera_image_complete",
            request_id=request_id,
            inference_ms=round(elapsed_ms, 2),
        )

        return Response(content=buffer.getvalue(), media_type="image/jpeg")

    except HTTPException:
        raise
    except Exception as e:
        log_event(
            "camera_image_error",
            level="ERROR",
            request_id=request_id,
            reason=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/predict/batch", response_model=BatchPredictResponse)
def predict_batch(request: BatchPredictRequest):
    request_id = str(uuid.uuid4())[:8]
    t_total = time.perf_counter()
    results = []

    log_event(
        "batch_predict_start",
        request_id=request_id,
        images=len(request.images_base64),
        model=request.model_name,
        confidence=request.confidence,
    )

    try:
        for img_b64 in request.images_base64:
            img = _decode_image(img_b64)
            result = _run_inference(
                img,
                request.model_name,
                request.confidence,
            )
            results.append(result)
            _metrics_update(total_delta=1, success_delta=1, total_ms_delta=result.inference_ms)

        total_ms = (time.perf_counter() - t_total) * 1000

        log_event(
            "batch_predict_complete",
            request_id=request_id,
            images=len(results),
            total_ms=round(total_ms, 2),
        )

        return BatchPredictResponse(
            results=results,
            total_inference_ms=round(total_ms, 2),
        )

    except Exception as e:
        log_event(
            "batch_predict_error",
            level="ERROR",
            request_id=request_id,
            reason=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    metrics = _metrics_read_for_response()
    avg = (
        metrics["total_ms"] / metrics["success"]
        if metrics["success"] > 0
        else 0.0
    )

    active_model = get_default_model_name()

    return MetricsResponse(
        total_requests=metrics["total"],
        successful_requests=metrics["success"],
        avg_inference_ms=round(avg, 2),
        model_name=active_model,
    )


@app.get("/stream/camera")
async def stream_camera(
    request: Request,
    confidence: float = Query(0.65, ge=0.0, le=1.0),
    model_name: str = Query("yolov8n_v4.pt"),
    framerate: int = Query(40, ge=1, le=60),
):
    """Transmite vídeo contínuo da câmera com detecções YOLO em todo frame.

    Durante todo o ciclo de vida do stream, as métricas Prometheus
    (yolo_stream_active, yolo_stream_fps, yolo_stream_frames_total,
    yolo_inference_time_seconds, yolo_detections_count, etc.) são atualizadas
    a cada frame processado, para que o Grafana acompanhe em tempo real.
    """

    if _streaming_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="Já existe um stream em andamento.",
        )

    model = None
    try:
        model = load_model(model_name)
    except Exception as exc:
        log_event(
            "stream_yolo_load_failed",
            level="WARN",
            model=model_name,
            reason=str(exc),
        )

    # Tamanho máximo que o buffer pode atingir antes de ser descartado
    # (evita crescimento indefinido caso os marcadores JPEG nunca sejam
    # encontrados, por exemplo por corrupção no stream do rpicam-vid).
    MAX_BUFFER_SIZE = 5 * 1024 * 1024  # 5 MB

    def run_inference(frame):
        """Executa a inferência YOLO quando o modelo estiver disponível. Senão devolve o frame bruto."""
        return _run_stream_or_camera_only(frame, model, confidence)

    async def frame_generator():
        async with _streaming_lock:

            STREAM_ACTIVE.set(1)
            fps_last_ts = time.perf_counter()
            fps_smoothed = 0.0

            cmd = ["rpicam-vid","-t", "0","-n","--codec", "mjpeg","--quality", "80","--width", "1280","--height", "720","--framerate", str(framerate),"-o", "-"]

            proc = None
            reader_task = None

            latest_frame_queue: asyncio.Queue = asyncio.Queue(maxsize=1)

            async def read_frames():
                """Lê o stdout do rpicam-vid continuamente e mantém
                sempre apenas o frame JPEG mais recente disponível."""

                loop = asyncio.get_running_loop()
                buffer = b""

                try:
                    while True:

                        chunk = await loop.run_in_executor(None, proc.stdout.read, 65536)                        

                        if not chunk:
                            break

                        buffer += chunk

                        if len(buffer) > MAX_BUFFER_SIZE:
                            log_event("stream_buffer_overflow",level="WARN",size=len(buffer),)
                            buffer = b""
                            continue

                        while True:
                            start = buffer.find(b"\xff\xd8")

                            if start == -1:
                                break

                            end = buffer.find(b"\xff\xd9",start + 2,)

                            if end == -1:
                                break

                            raw_frame = buffer[start:end + 2]
                            buffer = buffer[end + 2:]

                            if latest_frame_queue.full():
                                try:
                                    latest_frame_queue.get_nowait()
                                except asyncio.QueueEmpty:
                                    pass

                            await latest_frame_queue.put(raw_frame)

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log_event("stream_reader_error",level="ERROR",reason=str(e),)

            try:
                proc = subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,)
                log_event("stream_started", pid=proc.pid,model=model_name,confidence=confidence,)

                loop = asyncio.get_running_loop()
                reader_task = asyncio.create_task(read_frames())

                while True:

                    if await request.is_disconnected():
                        break

                    try:
                        raw_frame = await asyncio.wait_for(latest_frame_queue.get(),timeout=2.0,)
                    except asyncio.TimeoutError:
                        if reader_task.done() or proc.poll() is not None:
                            break
                        STREAM_FPS.set(0.0)
                        continue

                    try:
                        jpg = np.frombuffer(raw_frame,dtype=np.uint8,)
                        frame = cv2.imdecode(jpg,cv2.IMREAD_COLOR,)

                        if frame is None:
                            continue

                        frame = await loop.run_in_executor(
                            None,
                            run_inference,
                            frame,
                        )

                        success, encoded = cv2.imencode(
                            ".jpg",
                            frame,
                            [
                                cv2.IMWRITE_JPEG_QUALITY,
                                70,
                            ],
                        )

                        if not success:
                            continue

                        # Atualiza FPS entregue (média móvel exponencial)
                        # e contador de frames, para o Grafana acompanhar
                        # a saúde do stream em tempo real.
                        now = time.perf_counter()
                        instant_fps = 1.0 / max(now - fps_last_ts, 1e-6)
                        fps_smoothed = (
                            instant_fps if fps_smoothed == 0.0
                            else (0.8 * fps_smoothed + 0.2 * instant_fps)
                        )
                        fps_last_ts = now
                        STREAM_FPS.set(round(fps_smoothed, 2))

                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n"
                            + encoded.tobytes()
                            + b"\r\n"
                        )

                    except Exception as e:
                        log_event(
                            "stream_frame_error",
                            level="ERROR",
                            reason=str(e),
                        )

            finally:

                if reader_task is not None:
                    reader_task.cancel()
                    try:
                        await reader_task
                    except asyncio.CancelledError:
                        pass

                if proc is not None:

                    proc.terminate()

                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=2)

                    if proc.stderr:

                        stderr_output = (
                            proc.stderr.read()
                            .decode(errors="ignore")
                            .strip()
                        )

                        if stderr_output:
                            log_event(
                                "stream_camera_stderr",
                                level="WARN",
                                output=stderr_output,
                            )

                    log_event(
                        "stream_stopped",
                        pid=proc.pid,
                    )


    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/stream/view", response_class=HTMLResponse)
async def stream_view(request: Request):
    """Página para visualizar o stream anotado."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )