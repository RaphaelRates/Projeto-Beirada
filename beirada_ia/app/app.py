import asyncio
import io
import random
import shutil
import sys
from time import time

# pyrefly: ignore [missing-import]
from fastapi import HTTPException, Request, Response, Query
# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles

# pyrefly: ignore [missing-import]
from PIL import Image
# pyrefly: ignore [missing-import]
import numpy as np

from core.api_instance import app
from core.template_instance import templates
from model import get_default_model_name, load_model
from schemas import BatchPredictRequest, BatchPredictResponse, HealthResponse, MetricsResponse, PredictRequest, PredictResponse
from services.capture_image_service import _decode_image, _load_image_from_request
from services.inference_service import _run_inference
from services.log_service import log_event

# pyrefly: ignore [missing-import]
from fastapi.responses import StreamingResponse
# pyrefly: ignore [missing-import]
import subprocess

# pyrefly: ignore [missing-import]
import asyncio

# pyrefly: ignore [missing-import]
import cv2

from services.serial_service import enviar_classe, fechar_porta



_metrics = {"total": 0, "success": 0, "total_ms": 0.0}
_streaming_lock = asyncio.Lock()


app.mount(
    "/static",
    StaticFiles(directory="/app/static"),
    name="static"
)


@app.get("/stream/view")
async def stream_view(request: Request):
    classe_fake = random.randint(0, 3)
    enviado = enviar_classe(classe_fake)
    if enviado:
        log_event(
            "esp32_class_sent",
            backend="rpicam-vid",
            classe=classe_fake,
        )
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    model_name = get_default_model_name()
    try:
        load_model(model_name)
        loaded = True
    except Exception:
        loaded = False
    return HealthResponse(status="ok", model_loaded=loaded, model_name=model_name)

@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    _metrics["total"] += 1
    try:
        img = _load_image_from_request(request)
        result = _run_inference(img, request.model_name, request.confidence)
        _metrics["success"] += 1
        _metrics["total_ms"] += result.inference_ms
        return result
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict/image", responses={200: {"content": {"image/jpeg": {}}}})
def predict_image(request: PredictRequest):
    """Executa a inferência e retorna a imagem anotada em JPEG com cores 100% calibradas em RGB."""
    _metrics["total"] += 1
    try:
        # 1. Carrega imagem em RGB
        img_rgb = _load_image_from_request(request)
        model = load_model(request.model_name)
        
        t0 = time.perf_counter()
        results = model(img_rgb, conf=request.confidence, verbose=False)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        
        _metrics["success"] += 1
        _metrics["total_ms"] += elapsed_ms


        # 2. plot() retorna o array RGB anotado
        annotated_array = results[0].plot()
        
        # 3. Salva diretamente via PIL (RGB nativo da web, sem conversão indevida do OpenCV)
        annotated_pil = Image.fromarray(annotated_array)
        buffer = io.BytesIO()
        annotated_pil.save(buffer, format="JPEG", quality=95)


        return Response(content=buffer.getvalue(), media_type="image/jpeg")


    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict/batch", response_model=BatchPredictResponse)
def predict_batch(request: BatchPredictRequest):
    t_total = time.perf_counter()
    results = []
    for img_b64 in request.images_base64:
        img = _decode_image(img_b64)
        results.append(_run_inference(img, request.model_name, request.confidence))
    total_ms = (time.perf_counter() - t_total) * 1000
    return BatchPredictResponse(results=results, total_inference_ms=round(total_ms, 2))


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    avg = (_metrics["total_ms"] / _metrics["success"] if _metrics["success"] > 0 else 0.0)
    return MetricsResponse(
        total_requests=_metrics["total"],
        successful_requests=_metrics["success"],
        avg_inference_ms=round(avg, 2),
    )


@app.post("/esp32/enviar/{classe}")
async def esp32_enviar(classe: int):
    """Envia uma classe manualmente para o ESP32 via serial (útil para testes)."""
    if not (0 <= classe <= 9):
        raise HTTPException(status_code=400, detail="classe deve estar entre 0 e 9")

    ok = enviar_classe(classe, forcar=True)
    if not ok:
        raise HTTPException(
            status_code=503,
            detail="Falha ao enviar para o ESP32. Verifique a porta serial.",
        )
    return {"status": "ok", "classe": classe}


@app.on_event("shutdown")
async def _shutdown_serial():
    fechar_porta()


@app.get("/stream/camera")
async def stream_camera(
    request: Request,
    confidence: float = Query(0.25, ge=0.0, le=1.0, description="Limiar de confiança"),
    model_name: str = Query("yolov8n.pt", description="Modelo YOLO a ser utilizado"),
    framerate: int = Query(15, ge=1, le=30, description="FPS de captura solicitados ao sensor"),
):
    """Transmite vídeo contínuo da câmera com detecções YOLO sobrepostas.

    Cenários suportados automaticamente:
    - Linux (Raspberry Pi): usa rpicam-vid via subprocess para câmera CSI.
    - Windows: usa OpenCV (cv2.VideoCapture) para webcam USB.
    """
    if _streaming_lock.locked():
        log_event(
            "stream_rejected",
            level="WARN",
            reason="stream_already_running",
        )
        raise HTTPException(
            status_code=409,
            detail="Já existe um stream de câmera em andamento. Feche a aba atual antes de abrir outra.",
        )

    model = load_model(model_name)

    # ──────────────────────────────────────────────────────────────────────────
    # Cenário 1 — Linux / Raspberry Pi: rpicam-vid (câmera CSI via libcamera)
    # ──────────────────────────────────────────────────────────────────────────
    async def frame_generator_rpicam():
        async with _streaming_lock:
            cmd = [
                "rpicam-vid",
                "-t", "0",
                "-n",
                "--codec", "mjpeg",
                "--quality", "80",
                "--width", "640",
                "--height", "480",
                "--framerate", str(framerate),
                "-o", "-",
            ]

            proc = None

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                log_event(
                    "stream_started",
                    backend="rpicam-vid",
                    pid=proc.pid,
                    model=model_name,
                    confidence=confidence,
                    framerate=framerate,
                )

                loop = asyncio.get_running_loop()
                buffer = b""

                while True:
                    if await request.is_disconnected():
                        log_event(
                            "stream_client_disconnected",
                            pid=proc.pid,
                        )
                        break

                    try:
                        chunk = await asyncio.wait_for(
                            loop.run_in_executor(
                                None,
                                proc.stdout.read,
                                4096,
                            ),
                            timeout=5.0,
                        )
                    except asyncio.TimeoutError:
                        log_event(
                            "stream_timeout",
                            level="WARN",
                            pid=proc.pid,
                        )
                        break

                    if not chunk:
                        break

                    buffer += chunk

                    while True:
                        start = buffer.find(b"\xff\xd8")
                        if start == -1:
                            break

                        end = buffer.find(b"\xff\xd9", start + 2)
                        if end == -1:
                            break

                        raw_frame = buffer[start:end + 2]
                        buffer = buffer[end + 2:]

                        try:
                            img = Image.open(
                                io.BytesIO(raw_frame)
                            ).convert("RGB")
                            img_np = np.array(img)

                            results = model(
                                img_np,
                                conf=confidence,
                                verbose=False,
                            )

                            annotated = results[0].plot()
                            annotated_pil = Image.fromarray(annotated)

                            out_buffer = io.BytesIO()
                            annotated_pil.save(
                                out_buffer,
                                format="JPEG",
                                quality=85,
                            )

                            jpeg_bytes = out_buffer.getvalue()

                            classe_fake = random.randint(0, 3)
                            enviado = enviar_classe(classe_fake)
                            if enviado:
                                log_event(
                                    "esp32_class_sent",
                                    backend="opencv",
                                    classe=classe_fake,
                                )

                            yield (
                                b"--frame\r\n"
                                b"Content-Type: image/jpeg\r\n\r\n"
                                + jpeg_bytes
                                + b"\r\n"
                            )

                        except Exception as e:
                            log_event(
                                "stream_frame_error",
                                level="ERROR",
                                reason=str(e),
                            )

            finally:
                if proc is not None:
                    log_event(
                        "stream_stopping",
                        pid=proc.pid,
                    )

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

    # ──────────────────────────────────────────────────────────────────────────
    # Cenário 2 — Windows: OpenCV VideoCapture (webcam USB / índice 0)
    # ──────────────────────────────────────────────────────────────────────────
    async def frame_generator_opencv():
        async with _streaming_lock:
            cap = cv2.VideoCapture(0)

            if not cap.isOpened():
                log_event(
                    "stream_opencv_error",
                    level="ERROR",
                    reason="Não foi possível abrir a webcam (índice 0). Verifique se a câmera está conectada.",
                )
                return

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, framerate)

            log_event(
                "stream_started",
                backend="opencv",
                model=model_name,
                confidence=confidence,
                framerate=framerate,
            )

            loop = asyncio.get_running_loop()

            try:
                while True:
                    if await request.is_disconnected():
                        log_event("stream_client_disconnected", backend="opencv")
                        break

                    ret, frame_bgr = await loop.run_in_executor(None, cap.read)

                    if not ret:
                        log_event(
                            "stream_opencv_read_error",
                            level="WARN",
                            reason="cap.read() retornou False",
                        )
                        break

                    # OpenCV retorna BGR → converter para RGB para o YOLO/PIL
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

                    try:
                        results = model(
                            frame_rgb,
                            conf=confidence,
                            verbose=False,
                        )

                        annotated = results[0].plot()
                        annotated_pil = Image.fromarray(annotated)

                        out_buffer = io.BytesIO()
                        annotated_pil.save(
                            out_buffer,
                            format="JPEG",
                            quality=85,
                        )

                        jpeg_bytes = out_buffer.getvalue()
                        classe_fake = random.randint(0, 3)
                        enviado = enviar_classe(classe_fake)
                        if enviado:
                            log_event(
                                "esp32_class_sent",
                                backend="rpicam-vid",
                                classe=classe_fake,
                            )

                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n"
                            + jpeg_bytes
                            + b"\r\n"
                        )

                    except Exception as e:
                        log_event(
                            "stream_frame_error",
                            level="ERROR",
                            reason=str(e),
                        )

            finally:
                cap.release()
                log_event("stream_stopped", backend="opencv")

    has_rpicam = shutil.which("rpicam-vid") is not None
    generator = frame_generator_rpicam() if has_rpicam else frame_generator_opencv()
    selected_backend = "rpicam-vid" if has_rpicam else "opencv"

    log_event(
        "stream_backend_selected",
        backend=selected_backend,
        platform=sys.platform,
        rpicam_found=has_rpicam,
    )

    return Response(
        content="",
        media_type="text/plain",
    )