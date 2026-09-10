import json
import subprocess
import time
from model import get_default_model_name, load_model
from schemas import PredictResponse

from core.process_instance import _preprocessor

import numpy as np



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

