from app.model import get_default_model_name, load_model
from beirada_ia.app.schemas import PredictRequest, PredictResponse
from app.core.process_instance import _preprocessor
from beirada_ia.app.services.capture_image_service import _decode_image
from fastapi import HTTPException
from PIL import Image
from typing import Optional
import numpy as np
import httpx
import io
import subprocess

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
                "--width", "640",
                "--height", "480",
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


def _decode_image(image_base64: str) -> np.ndarray:
    raw = base64.b64decode(image_base64)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    return np.array(img)