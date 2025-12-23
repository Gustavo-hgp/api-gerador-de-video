import os
import time
import mimetypes
from urllib.parse import urlparse
from typing import List, Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, HttpUrl

from google import genai
from google.genai import types

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise RuntimeError("GOOGLE_API_KEY não encontrada no .env")

client = genai.Client()
app = FastAPI(title="Veo Video Generator API", version="1.1.0")

TMP_DIR = os.getenv("TMP_DIR", "tmp_videos")
os.makedirs(TMP_DIR, exist_ok=True)


# =========================
# MODELS
# =========================
class GenerateVideoRequest(BaseModel):
    prompt: str = Field(..., min_length=3)
    reference_image_urls: List[HttpUrl] = Field(default_factory=list, max_items=3)
    model: str = Field(default="veo-3.1-generate-preview")


# =========================
# HELPERS
# =========================
def _infer_mime_from_url(url: str) -> str:
    path = urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    return mimetypes.types_map.get(ext, "image/jpeg")


def load_image_from_url_as_types_image(url: str) -> types.Image:
    resp = requests.get(str(url), timeout=30)
    resp.raise_for_status()

    mime = resp.headers.get("Content-Type", "")
    mime = mime.split(";")[0].strip() if mime else ""
    if not mime:
        mime = _infer_mime_from_url(str(url))

    return types.Image(image_bytes=resp.content, mime_type=mime)


def build_reference_images(urls: List[str]) -> List[types.VideoGenerationReferenceImage]:
    refs: List[types.VideoGenerationReferenceImage] = []
    for u in urls[:3]:
        img = load_image_from_url_as_types_image(u)
        refs.append(
            types.VideoGenerationReferenceImage(
                image=img,
                reference_type="asset",
            )
        )
    return refs


def wait_operation_done(operation_name: str, poll_seconds: int, timeout_seconds: int) -> types.GenerateVideosOperation:
    start = time.time()
    op = types.GenerateVideosOperation(name=operation_name)

    while True:
        op = client.operations.get(op)
        if getattr(op, "done", False):
            break

        if time.time() - start > timeout_seconds:
            raise HTTPException(status_code=408, detail="Timeout esperando a geração do vídeo.")
        time.sleep(poll_seconds)

    # Mitiga: done=True mas response ainda None
    for _ in range(6):
        op = client.operations.get(op)

        if getattr(op, "error", None):
            raise HTTPException(status_code=500, detail=f"Video generation failed: {op.error}")

        resp = getattr(op, "response", None)
        vids = getattr(resp, "generated_videos", None) if resp else None
        if vids:
            return op

        time.sleep(5)

    raise HTTPException(status_code=500, detail="Operation finalizou, mas não retornou generated_videos.")


def save_video_to_tempfile(operation: types.GenerateVideosOperation, out_path: str) -> str:
    resp = getattr(operation, "response", None)
    vids = getattr(resp, "generated_videos", None) if resp else None
    if not vids:
        raise HTTPException(status_code=500, detail="Sem generated_videos no response.")

    generated_video = vids[0]

    # Baixa o arquivo (prepara o handle)
    client.files.download(file=generated_video.video)

    # Salva em disco (pra servir via streaming sem estourar memória)
    generated_video.video.save(out_path)
    return out_path


def _cleanup_file(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


# =========================
# ROUTE QUE RETORNA O MP4 DIRETO
# =========================
@app.post("/videos/stream")
def generate_video_stream(
    payload: GenerateVideoRequest,
    background_tasks: BackgroundTasks,
    poll_seconds: int = Query(default=10, ge=2, le=60),
    timeout_seconds: int = Query(default=900, ge=60, le=3600),
):
    if len(payload.reference_image_urls) > 3:
        raise HTTPException(status_code=400, detail="Máximo de 3 imagens de referência.")

    try:
        reference_images = build_reference_images([str(u) for u in payload.reference_image_urls])

        operation = client.models.generate_videos(
            model=payload.model,
            prompt=payload.prompt,
            config=types.GenerateVideosConfig(reference_images=reference_images),
        )

        operation_name = operation.name

        op_done = wait_operation_done(operation_name, poll_seconds=poll_seconds, timeout_seconds=timeout_seconds)

        # Nome seguro pro arquivo temporário
        safe = operation_name.replace("/", "_").replace(":", "_")
        out_path = os.path.join(TMP_DIR, f"{safe}.mp4")

        save_video_to_tempfile(op_done, out_path)

        # agenda remoção do arquivo após a resposta terminar
        background_tasks.add_task(_cleanup_file, out_path)

        return FileResponse(
            path=out_path,
            media_type="video/mp4",
            filename=f"{safe}.mp4",
            headers={
                "Cache-Control": "no-store",
            },
        )

    except requests.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"Erro ao baixar imagem de referência: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
