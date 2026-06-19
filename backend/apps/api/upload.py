"""Upload API endpoints — /v1/upload/

Images are stored under UPLOAD_DIR/<user_id>/<snowflake>.<ext> and served
publicly at UPLOAD_BASE_URL (mounted as StaticFiles in main.py). The returned
url is embedded into note_content as standard Markdown image syntax.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from backend.apps.model.user import User
from backend.apps.utils.config import settings
from backend.apps.utils.exceptions import BusinessError
from backend.apps.utils.security import get_current_user
from backend.apps.utils.snowflake import snowflake_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/upload", tags=["Upload"])

# FastAPI streaming reads chunks; cap how much we buffer to keep a sane memory
# ceiling even if the client lies about Content-Length.
_READ_CHUNK = 1024 * 1024  # 1 MiB


class UploadImageResponse(BaseModel):
    url: str
    filename: str
    size: int
    mime: str | None = None


@router.post("/image", response_model=UploadImageResponse, summary="上传图片")
async def upload_image(
    file: UploadFile = File(..., description="图片文件"),
    user: User = Depends(get_current_user),
):
    """Upload a single image. Files are isolated per user and named with a
    Snowflake ID so the URL is not enumerable. Validation is by extension +
    size; the content is not re-encoded."""
    # ── Extension whitelist ────────────────────────────────────────────────
    original_name = file.filename or ""
    ext = Path(original_name).suffix.lower().lstrip(".")
    allowed = settings.UPLOAD_ALLOWED_EXT_LIST
    if not ext or ext not in allowed:
        raise BusinessError(f"不支持的图片类型,仅允许 {','.join(sorted(allowed))}")

    # ── Read + size cap ────────────────────────────────────────────────────
    max_bytes = settings.UPLOAD_MAX_SIZE_MB * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            await file.close()
            raise BusinessError(f"图片大小超过 {settings.UPLOAD_MAX_SIZE_MB}MB 限制")
        chunks.append(chunk)
    content_bytes = b"".join(chunks)
    await file.close()

    if total == 0:
        raise BusinessError("图片文件为空")

    # ── Persist ────────────────────────────────────────────────────────────
    image_id = snowflake_id()
    filename = f"{image_id}.{ext}"
    user_dir = Path(settings.UPLOAD_DIR) / str(user.user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    dest = user_dir / filename
    dest.write_bytes(content_bytes)

    url = f"{settings.UPLOAD_BASE_URL.rstrip('/')}/{user.user_id}/{filename}"
    logger.info(
        "Upload image: user_id=%s, file=%r -> %s (%d bytes)",
        user.user_id, original_name, url, total,
    )
    return UploadImageResponse(
        url=url,
        filename=filename,
        size=total,
        mime=file.content_type,
    )
