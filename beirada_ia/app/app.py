import asyncio
import base64
import io
import json
import subprocess
import time
import uuid

import cv2
import httpx
import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
# from model import get_default_model_name, load_model
from PIL import Image
from app.schemas import (
    BatchPredictRequest,
    BatchPredictResponse,
    Detection,
    HealthResponse,
    MetricsResponse,
    PredictRequest,
    PredictResponse,
)
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# from preprocessing.preprocessor import CONFIG_DEFAULT, Preprocessor

app = FastAPI(
    title="YOLO Inference API",
    description="API REST para inferência com YOLOv8 e Câmera no Raspberry Pi 5",
    version="1.1.0",
)

_metrics = {"total": 0, "success": 0, "total_ms": 0.0}
_streaming_lock = asyncio.Lock()

templates = Jinja2Templates(directory="app/templates")

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static"
)


@app.get("/stream/view")
async def stream_view(request: Request):
    return templates.TemplateResponse(
        "stream.html",
        {"request": request}
    )

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


@app.get("/login")
async def login(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )

@app.get("/dashboard")
async def login(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={}
    )

@app.get("/users")
async def login(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={}
    )
