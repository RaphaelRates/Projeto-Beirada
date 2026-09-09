import asyncio

from fastapi import Request
from fastapi.staticfiles import StaticFiles

# from model import get_default_model_name, load_model
from app.core.api_instance import app
from app.core.template_instance import templates

_metrics = {"total": 0, "success": 0, "total_ms": 0.0}
_streaming_lock = asyncio.Lock()


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
        name="login.html",
        context={}
    )
