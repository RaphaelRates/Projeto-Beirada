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

templates = Jinja2Templates(directory="templates")

GRAFANA_CLOUD_ENDPOINT = os.getenv("GRAFANA_CLOUD_ENDPOINT") or os.getenv("GRAFANA_CLOUD_LOKI_URL") or ""
GRAFANA_CLOUD_TOKEN = os.getenv("GRAFANA_CLOUD_TOKEN") or os.getenv("GRAFANA_CLOUD_API_KEY") or ""
GRAFANA_CLOUD_USERNAME = os.getenv("GRAFANA_CLOUD_USERNAME") or ""
GRAFANA_CLOUD_PASSWORD = os.getenv("GRAFANA_CLOUD_PASSWORD") or ""

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
    if not _metrics_file.parent.exists():
        _metrics_file.parent.mkdir(parents=True, exist_ok=True)

    if not _metrics_file.exists():
        _metrics_save(_metrics_default())


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
    _metrics_ensure_file()
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


def _grafana_cloud_build_payload(result: PredictResponse, request_id: str, confidence: float, model_name: str):
    """Serializa o schema de resposta de detecção em um envelope JSON útil para Loki/Grafana Cloud."""
    detections = []
    for d in result.detections:
        detections.append({
            "label": d.label,
            "confidence": d.confidence,
            "bbox": d.bbox,
        })

    payload = {
        "request_id": request_id,
        "model_name": model_name,
        "model_used": result.model_used,
        "confidence": confidence,
        "inference_ms": result.inference_ms,
        "image_width": result.image_width,
        "image_height": result.image_height,
        "detections": detections,
    }

    return {
        "streams": [
            {
                "stream": {
                    "job": "beirada-inference",
                    "source": "app.py",
                    "model": result.model_used,
                },
                "values": [
                    [
                        str(int(time.time() * 1_000_000_000)),
                        json.dumps(payload, ensure_ascii=False),
                    ]
                ],
            }
        ]
    }


def _send_to_grafana_cloud(result: PredictResponse, request_id: str, confidence: float, model_name: str):
    """Envia o envelope da resposta como log/metric para Grafana Cloud quando a URL/token estiverem configurados."""
    if not GRAFANA_CLOUD_ENDPOINT:
        return

    payload = _grafana_cloud_build_payload(result, request_id, confidence, model_name)
    headers = {"Content-Type": "application/json"}

    if GRAFANA_CLOUD_TOKEN:
        headers["Authorization"] = f"Bearer {GRAFANA_CLOUD_TOKEN}"
    elif GRAFANA_CLOUD_USERNAME and GRAFANA_CLOUD_PASSWORD:
        token = base64.b64encode(f"{GRAFANA_CLOUD_USERNAME}:{GRAFANA_CLOUD_PASSWORD}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"

    try:
        # Endpoint Loki / Grafana Cloud Logs espera um POST de streams com arrays de valores.
        httpx.post(
            GRAFANA_CLOUD_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=5.0,
        )
    except Exception as exc:
        log_event(
            "grafana_cloud_export_error",
            level="ERROR",
            reason=str(exc),
            request_id=request_id,
            model=model_name,
        )


def _run_stream_or_camera_only(frame: np.ndarray, model, confidence: float):
    """Fallback simples: se o YOLO não puder rodar, devolve o frame bruto da câmera.

    Isso mantém o stream vivo mesmo quando o modelo offline ou indisponível.
    """
    if model is None:
        return frame

    try:
        results = model.predict(
            source=frame,
            conf=confidence,
            imgsz=300,
            verbose=False,
            half=True,
            iou=0.15, 
            
        )
        return results[0].plot()
    except Exception as exc:
        log_event(
            "stream_yolo_fallback_camera_only",
            level="WARN",
            reason=str(exc),
            confidence=confidence,
        )
        return frame


def log_event(event: str, level: str = "INFO", **kwargs):
    """Emite um evento estruturado em JSON para stdout."""
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "level": level,
        "event": event,
        **kwargs,
    }
    print(json.dumps(record, ensure_ascii=False), flush=True)


_preprocessor = Preprocessor(CONFIG_DEFAULT)   # instância global

def _run_inference(image_np: np.ndarray, model_name: str, confidence: float) -> PredictResponse:
    model = load_model(model_name)


    # Pré-processamento explícito
    # image_np chega em RGB (já convertido em _decode_image) --
    # o Preprocessor espera BGR, então converte temporariamente
    frame_bgr   = image_np[:, :, ::-1]
    preproc_res = _preprocessor.process(frame_bgr)
    frame_ready = preproc_res.frame  # RGB, letterboxed


    t0 = time.perf_counter()
    results = model(frame_ready, conf=confidence, verbose=False)
    elapsed_ms = (time.perf_counter() - t0) * 1000


    detections = []
    for r in results:
        for box in r.boxes:
            # Ajusta as coordenadas do espaço letterboxed de volta ao
            # espaço da imagem original -- sem isso, os bboxes retornados
            # pela API ficam deslocados sempre que houver padding
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
        resp = httpx.get(
            request.image_url,
            timeout=15.0,
            follow_redirects=True,
        )
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


def _run_inference(
    image_np: np.ndarray,
    model_name: str,
    confidence: float,
) -> PredictResponse:
    model = load_model(model_name)
    t0 = time.perf_counter()
    results = model(image_np, conf=confidence, verbose=False)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    detections = []
    for r in results:
        for box in r.boxes:
            coords = box.xyxy[0].tolist()
            cls_id = int(box.cls[0].item())
            conf_val = float(box.conf[0].item())
            detections.append(
                Detection(
                    label=model.names[cls_id],
                    confidence=round(conf_val, 4),
                    bbox=[round(float(c), 2) for c in coords],
                )
            )

    h, w = image_np.shape[:2]
    return PredictResponse(
        detections=detections,
        inference_ms=round(elapsed_ms, 2),
        model_used=model_name,
        image_width=w,
        image_height=h,
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
        _send_to_grafana_cloud(result, request_id, request.confidence, request.model_name)

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
        _send_to_grafana_cloud(result, request_id, confidence, model_name)

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
            _send_to_grafana_cloud(result, request_id, request.confidence, request.model_name)

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
    """Transmite vídeo contínuo da câmera com detecções YOLO em todo frame."""

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

            cmd = [
                "rpicam-vid",
                "-t", "0",
                "-n",
                "--codec", "mjpeg",
                "--quality", "80",
                "--width", "1300",
                "--height", "720",
                "--framerate", str(framerate),
                "-o", "-"
            ]

            proc = None
            reader_task = None

            # Fila com tamanho 1: guarda só o frame mais recente.
            # Se um frame novo chegar antes do anterior ser consumido,
            # o anterior é descartado. Isso evita que o delay cresça
            # indefinidamente quando a inferência é mais lenta que a
            # taxa de captura.
            latest_frame_queue: asyncio.Queue = asyncio.Queue(maxsize=1)

            async def read_frames():
                """Lê o stdout do rpicam-vid continuamente e mantém
                sempre apenas o frame JPEG mais recente disponível."""

                loop = asyncio.get_running_loop()
                buffer = b""

                try:
                    while True:

                        chunk = await loop.run_in_executor(
                            None,
                            proc.stdout.read,
                            65536,
                        )

                        if not chunk:
                            break

                        buffer += chunk

                        if len(buffer) > MAX_BUFFER_SIZE:
                            log_event(
                                "stream_buffer_overflow",
                                level="WARN",
                                size=len(buffer),
                            )
                            buffer = b""
                            continue

                        while True:

                            start = buffer.find(b"\xff\xd8")

                            if start == -1:
                                break

                            end = buffer.find(
                                b"\xff\xd9",
                                start + 2,
                            )

                            if end == -1:
                                break

                            raw_frame = buffer[start:end + 2]
                            buffer = buffer[end + 2:]

                            # Descarta o frame antigo (se houver) antes
                            # de colocar o novo, garantindo que a fila
                            # nunca acumule atraso.
                            if latest_frame_queue.full():
                                try:
                                    latest_frame_queue.get_nowait()
                                except asyncio.QueueEmpty:
                                    pass

                            await latest_frame_queue.put(raw_frame)

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log_event(
                        "stream_reader_error",
                        level="ERROR",
                        reason=str(e),
                    )

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )

                log_event(
                    "stream_started",
                    pid=proc.pid,
                    model=model_name,
                    confidence=confidence,
                )

                loop = asyncio.get_running_loop()
                reader_task = asyncio.create_task(read_frames())

                while True:

                    if await request.is_disconnected():
                        break

                    try:
                        raw_frame = await asyncio.wait_for(
                            latest_frame_queue.get(),
                            timeout=2.0,
                        )
                    except asyncio.TimeoutError:
                        # Sem frames novos há 2s: verifica se o processo
                        # ou a leitura morreram, senão continua esperando.
                        if reader_task.done() or proc.poll() is not None:
                            break
                        continue

                    try:

                        jpg = np.frombuffer(
                            raw_frame,
                            dtype=np.uint8,
                        )

                        frame = cv2.imdecode(
                            jpg,
                            cv2.IMREAD_COLOR,
                        )

                        if frame is None:
                            continue

                        # Detecção em thread separada para não bloquear
                        # o event loop enquanto o modelo processa.
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


from fastapi import Request
from fastapi.responses import HTMLResponse

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/stream/view", response_class=HTMLResponse)
async def stream_view(request: Request):
    """Página para visualizar o stream anotado."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )