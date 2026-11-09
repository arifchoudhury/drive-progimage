import mimetypes
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from app.core.auth import require_auth
from app.core.rate_limit import enforce_rate_limit
from app.images.api.dependencies import ImageServiceDep
from app.images.api.schemas import ImageListResponse, ImageSummary, ImageUploadResponse
from app.images.domain.exceptions import (
    ImageNotFoundError,
    ImageRejectedError,
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageFormatError,
)
from app.images.domain.validation import DEFAULT_ALLOWED_FORMATS

# Rate limit first, so failed logins count too (it also caps password guessing). Then the TEMPORARY
# shared-credential Basic auth on every image endpoint; see app/core/auth.py.
router = APIRouter(
    prefix="/images",
    tags=["images"],
    dependencies=[Depends(enforce_rate_limit), Depends(require_auth)],
    responses={status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Rate limit exceeded; see Retry-After"}},
)

_ACCEPTED = ", ".join(sorted(DEFAULT_ALLOWED_FORMATS))

_UPLOAD_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_413_CONTENT_TOO_LARGE: {"description": "The upload exceeds the size limit"},
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"description": f"A real image, but not one of: {_ACCEPTED}"},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Missing file, not an image, corrupt, or too many pixels"},
}


# We serve user-uploaded bytes from our own origin, so a browser must only ever treat them as an image: no type
# sniffing, nothing runs or loads if they render as a document. Images never change once stored, so they cache
# for a year; `private` because the endpoint is behind auth.
_SERVE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "private, max-age=31536000, immutable",
}


def _rejection_to_http(exc: ImageRejectedError) -> HTTPException:
    match exc:
        case ImageTooLargeError(max_bytes=limit):
            return HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Image exceeds the {limit}-byte limit")
        case UnsupportedImageFormatError(image_format=fmt):
            return HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Unsupported image format {fmt}; accepted: {_ACCEPTED}"
            )
        case InvalidImageError() | ImageRejectedError():
            return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "File is not a valid image")


@router.post("", status_code=status.HTTP_201_CREATED, responses=_UPLOAD_RESPONSES)
def upload_image(file: Annotated[UploadFile, File()], service: ImageServiceDep) -> ImageUploadResponse:
    # Bounded: MaxBodySizeMiddleware has already refused any request body over the limit.
    try:
        image_id = service.upload(file.file.read(), file.filename)
    except ImageRejectedError as exc:
        raise _rejection_to_http(exc) from exc
    return ImageUploadResponse(id=image_id)


@router.get("")
def list_images(service: ImageServiceDep) -> ImageListResponse:
    # TODO(pagination): returns every image. Add `limit` and `cursor` query params, then a `next_cursor` field.
    return ImageListResponse(items=[ImageSummary.model_validate(i, from_attributes=True) for i in service.list()])


@router.get(
    "/{image_id}", response_class=Response, responses={status.HTTP_404_NOT_FOUND: {"description": "No such image"}}
)
def get_image(image_id: uuid.UUID, service: ImageServiceDep, response: Response) -> Response:
    try:
        image = service.get(image_id)
    except ImageNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found") from exc
    # A returned Response skips FastAPI's merge of dependency-set headers (RateLimit-*), so carry them over.
    # The download name is generated, never the client's filename.
    extension = mimetypes.guess_extension(image.content_type) or ""
    headers = {
        **response.headers,
        **_SERVE_HEADERS,
        "Content-Disposition": f'inline; filename="{image_id}{extension}"',
    }
    return Response(content=image.data, media_type=image.content_type, headers=headers)
