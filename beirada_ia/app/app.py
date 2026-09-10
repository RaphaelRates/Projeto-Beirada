import asyncio
import io
from time import time

from fastapi import HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles

from PIL import Image

from core.api_instance import app
from core.template_instance import templates
from model import get_default_model_name, load_model
from schemas import BatchPredictRequest, BatchPredictResponse, HealthResponse, MetricsResponse, PredictRequest, PredictResponse
from services.capture_image_service import _decode_image, _load_image_from_request
from services.inference_service import _run_inference

_metrics = {"total": 0, "success": 0, "total_ms": 0.0}
_streaming_lock = asyncio.Lock()


app.mount(
    "/static",
    StaticFiles(directory="/app/static"),
    name="static"
)


@app.get("/stream/view")
async def stream_view(request: Request):
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

