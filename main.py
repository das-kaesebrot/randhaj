import asyncio
import logging
import os
import time
import traceback
from typing import Union, Annotated
import crawleruseragents
import shutil
from fastapi import APIRouter, FastAPI, HTTPException, Request, UploadFile, Form
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.exception_handlers import http_exception_handler
from http import HTTPStatus
from kaesebrot_commons.logging.utils import LoggingUtils
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from pathlib import Path

from api.cache import Cache
from api.classes import (
    FaviconResponse,
    HealthCheckResponse,
    ImagePageResponse,
    ResolutionVariant,
    StaticFilesCustomHeaders,
    TemplateResolutionMetadata,
)
from api.utils.image import ImageProcessor
from api.constants import Constants

ENV_PREFIX = "RANDHAJ"

STATIC_EXTERNAL_CACHING_TIME = 365 * 24 * 60 * 60  # 365 days in seconds
IMAGE_FILES_CACHING_TIME = 30 * 24 * 60 * 60  # 30 days in seconds

API_PAGE_SIZE_LIMIT = 200
VIEW_PAGE_SIZE_LIMIT = 50

ALLOWED_MAX_UPLOAD_FILE_SIZE = 4 * 1024 * 1024
ALLOWED_UPLOAD_CONTENT_TYPES = ["image/png", "image/jpeg"]

version = os.getenv("APP_VERSION", "local-dev")
source_image_dir = os.getenv(f"{ENV_PREFIX}_IMAGE_DIR", "assets/images")
cache_dir = os.getenv(f"{ENV_PREFIX}_CACHE_DIR", "cache")
cache_db_file = os.getenv(f"{ENV_PREFIX}_CACHE_DB_FILE", f"{cache_dir.rstrip("/")}/.randhaj-cache.db")
submissions_dir = os.getenv(f"{ENV_PREFIX}_SUBMISSIONS_DIR", "submissions")
max_submissions_usage = float(
    os.getenv(f"{ENV_PREFIX}_SUBMISSIONS_DIR_DISK_USAGE_LIMIT", "0.9")
)
site_title = os.getenv(f"{ENV_PREFIX}_SITE_TITLE", "Random image")
site_emoji = os.getenv(f"{ENV_PREFIX}_SITE_EMOJI", "🦈")
default_card_image_id = os.getenv(f"{ENV_PREFIX}_DEFAULT_CARD_IMAGE")
max_initial_cache_generator_workers = int(
    os.getenv(f"{ENV_PREFIX}_MAX_INITIAL_CACHE_GENERATOR_WORKERS", 4)
)
loglevel = os.getenv(
    f"{ENV_PREFIX}_LOG_LEVEL", os.getenv("UVICORN_LOG_LEVEL", logging.INFO)
)

LoggingUtils.setup_logging_with_default_formatter(loglevel=loglevel)

for name in logging.root.manager.loggerDict.keys():
    logging.getLogger(name).handlers = []
    logging.getLogger(name).propagate = True

tags_metadata = [
    {
        "name": "view",
        "description": "Routes for the web UI. Always returns an HTML page.",
    },
    {
        "name": "api",
        "description": "REST API for retrieving images and service status. Depending on the route either `application/json` or `image/png` is returned.",
    },
]

app = FastAPI(
    title=site_title,
    version=version,
    license_info={
        "name": "GPL-2.0",
        "url": "https://github.com/das-kaesebrot/randhaj/blob/main/LICENSE",
    },
    openapi_tags=tags_metadata,
)
app.mount(
    "/static/dist",
    StaticFilesCustomHeaders(
        directory="resources/static",
        headers={
            "Cache-Control": f"public, max-age={STATIC_EXTERNAL_CACHING_TIME}, s-maxage={STATIC_EXTERNAL_CACHING_TIME}, immutable"
        },
    ),
    name="static_external",
)
templates = Jinja2Templates(directory="resources/templates")

api_router = APIRouter(tags=["api"])
view_router = APIRouter(tags=["view"], default_response_class=HTMLResponse)

cache = Cache(
    image_dir=source_image_dir,
    cache_dir=cache_dir,
    max_initial_cache_generator_workers=max_initial_cache_generator_workers,
    connection_string=f"sqlite:///{cache_db_file}"
)
cache_start = asyncio.create_task(cache.start())

if not default_card_image_id:
    default_card_image_id = cache.get_first_id()


def ns_to_duration_str(ns: int) -> str:
    unit_prefix = ["n", "μ", "m", "", "k", "M", "G"]
    duration = ns
    iteration = 0

    while duration >= 1000:
        duration /= 1000
        iteration += 1

        if iteration >= len(unit_prefix) - 1:
            iteration = len(unit_prefix) - 1

    return f"{duration:.2f} {unit_prefix[iteration]}s"


def get_file_response(
    *,
    image_id: str,
    width: Union[int, None] = None,
    height: Union[int, None] = None,
    download: bool = False,
    set_cache_header: bool = True,
    square: bool = False,
) -> FileResponse:
    if not cache.id_exists(image_id):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"File with id='{image_id}' could not be found!",
        )

    metadata = cache.get_metadata(image_id)

    if square:
        if not width:
            width = Constants.get_max_width()
        height = width

    if not height and width and width not in Constants.ALLOWED_DIMENSIONS:
        _, height = ImageProcessor.calculate_scaled_size(
            original_width=metadata.original_width,
            original_height=metadata.original_height,
            width=width,
        )
        if height not in Constants.ALLOWED_DIMENSIONS:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Width is not of allowed value!",
            )

    if not width and height and height not in Constants.ALLOWED_DIMENSIONS:
        width, _ = ImageProcessor.calculate_scaled_size(
            original_width=metadata.original_width,
            original_height=metadata.original_height,
            height=height,
        )

        if width not in Constants.ALLOWED_DIMENSIONS:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Height is not of allowed value!",
            )

    filename = cache.get_filename(image_id, width=width, height=height, square=square)

    headers = {
        "Content-Disposition": (
            "inline"
            if not download
            else f'attachment; filename="{os.path.basename(filename)}"'
        ),
        "X-Image-Id": f"{image_id}",
    }

    if set_cache_header:
        headers["Cache-Control"] = (
            f"max-age={IMAGE_FILES_CACHING_TIME}, s-maxage={IMAGE_FILES_CACHING_TIME}, public, no-transform, immutable"
        )

    return FileResponse(
        path=filename,
        media_type=metadata.media_type,
        headers=headers,
    )


def get_image_page_response(
    request: Request, image_id: str, is_direct_request: bool = False
) -> HTMLResponse:
    start = time.perf_counter_ns()
    if not cache.id_exists(image_id):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Image with id='{image_id}' could not be found!",
        )

    if crawleruseragents.is_crawler(user_agent=request.headers.get("user-agent")):
        return templates.TemplateResponse(
            request=request,
            name="base.html",
            context={
                "site_emoji": site_emoji,
                "site_title": site_title,
                "image_id": image_id,
                "is_direct_request": is_direct_request,
                "default_card_image_id": default_card_image_id,
                "thumbnail_width": Constants.get_small_thumbnail_width(),
            },
        )

    current_width = Constants.get_default_width()
    metadata = cache.get_metadata(image_id)
    current_width, current_height = ImageProcessor.calculate_scaled_size(
        original_width=metadata.original_width,
        original_height=metadata.original_height,
        width=current_width,
    )
    filename = cache.get_filename(image_id, width=current_width, height=current_height)
    filename = os.path.basename(filename)

    variants = []
    for width in sorted(Constants.ALLOWED_DIMENSIONS, reverse=True):
        width, height = ImageProcessor.calculate_scaled_size(
            original_width=metadata.original_width,
            original_height=metadata.original_height,
            width=width,
        )
        current = False

        if width == current_width:
            current = True

        filename = os.path.basename(
            cache.get_filename(
                id=image_id,
                width=width,
                height=height,
                square=False,
                only_get_filename=True,
            )
        )
        variants.append(
            ResolutionVariant(
                width=width, height=height, current=current, filename=filename
            )
        )

    resolution_data = TemplateResolutionMetadata(
        current_width=current_width,
        current_height=current_height,
        variant_ladder=variants,
    )

    return templates.TemplateResponse(
        request=request,
        name="image.html",
        context={
            "site_emoji": site_emoji,
            "site_title": site_title,
            "image_id": image_id,
            "image_filename": filename,
            "version": version,
            "resolution_data": resolution_data,
            "is_direct_request": is_direct_request,
            "default_card_image_id": default_card_image_id,
            "thumbnail_width": Constants.get_small_thumbnail_width(),
            "nav_page": "image",
            "request_duration": ns_to_duration_str(time.perf_counter_ns() - start),
            "background_image_id": image_id,
            "background_image_width": Constants.get_background_width(),
        },
    )


def get_gallery_page_response(
    request: Request,
    page: int = 1,
    page_size=VIEW_PAGE_SIZE_LIMIT,
) -> HTMLResponse:
    start = time.perf_counter_ns()
    if page < 1:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="Page can't be smaller than 1!"
        )

    if page_size > VIEW_PAGE_SIZE_LIMIT:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Page size can't be bigger than {VIEW_PAGE_SIZE_LIMIT}!",
        )

    page_max = (cache.get_total_image_count() // page_size) + 1
    if page > page_max:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Page can't be bigger than {page_max}!",
        )

    ids = cache.get_ids_paged(page=page - 1, page_size=page_size)
    current_width = Constants.get_small_thumbnail_width()

    return templates.TemplateResponse(
        request=request,
        name="gallery.html",
        context={
            "site_emoji": site_emoji,
            "site_title": site_title,
            "version": version,
            "default_card_image_id": default_card_image_id,
            "thumbnail_width": Constants.get_small_thumbnail_width(),
            "image_ids": ids,
            "current_width": current_width,
            "page_num": page,
            "page_max": page_max,
            "page_size": page_size,
            "nav_page": "gallery",
            "request_duration": ns_to_duration_str(time.perf_counter_ns() - start),
            "background_image_id": default_card_image_id,
            "background_image_width": Constants.get_background_width(),
        },
    )


def get_submit_page_response(
    request: Request,
) -> HTMLResponse:
    start = time.perf_counter_ns()

    return templates.TemplateResponse(
        request=request,
        name="submit.html",
        context={
            "site_emoji": site_emoji,
            "site_title": site_title,
            "version": version,
            "default_card_image_id": default_card_image_id,
            "nav_page": "submit",
            "request_duration": ns_to_duration_str(time.perf_counter_ns() - start),
            "background_image_id": default_card_image_id,
            "background_image_width": Constants.get_background_width(),
        },
    )


@view_router.get(
    "/favicon.ico", summary="Returns the favicon", response_class=FaviconResponse
)
async def get_favicon():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        + f'<text y=".9em" font-size="90">{site_emoji}</text>'
        + "</svg>"
    )


@view_router.get(
    "/", summary="Returns the page for a random image", response_class=HTMLResponse
)
async def page_redirect_rand_image(request: Request):
    image_id = cache.get_random_id()
    return get_image_page_response(request, image_id)


@view_router.get(
    "/gallery",
    summary="Returns the specified gallery page. Page starts at 1.",
    response_class=HTMLResponse,
)
async def page_get_gallery(request: Request, page: int = 1, page_size: int = 50):
    return get_gallery_page_response(request, page, page_size)


@view_router.get(
    "/submit",
    summary="Returns the submissions page.",
    response_class=HTMLResponse,
)
async def page_get_submit(request: Request):
    return get_submit_page_response(request)


@view_router.post(
    "/submit",
    summary="Submits a new image.",
    response_class=HTMLResponse,
)
async def page_post_submit(
    request: Request,
    file: UploadFile,
    accept_conditions: Annotated[bool, Form()],
):
    if not accept_conditions:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"I'm sorry, but you have to accept the conditions!",
        )

    if file.size > ALLOWED_MAX_UPLOAD_FILE_SIZE:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Image size can't be bigger than {ALLOWED_MAX_UPLOAD_FILE_SIZE} byte!",
        )

    if file.content_type not in ALLOWED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Image has to have a content type of {ALLOWED_UPLOAD_CONTENT_TYPES}",
        )

    total, used, free = shutil.disk_usage(Path(submissions_dir).absolute().as_posix())
    used_amount = used / total
    if used_amount > max_submissions_usage:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Disk usage is above allowed amount!",
        )

    id = None
    try:
        await file.seek(0)
        contents = BytesIO(await file.read())
        with Image.open(contents) as image:
            id, metadata = (
                ImageProcessor.convert_to_unified_format_and_write_to_filesystem(
                    output_path=submissions_dir, image=image, format_save_properties={ "quality": 100 }, filename_prefix="submission"
                )
            )
    except UnidentifiedImageError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Bad image! {e.strerror}",
        )

    return templates.TemplateResponse(
        request=request,
        name="submit-success.html",
        context={
            "site_emoji": site_emoji,
            "site_title": site_title,
            "version": version,
            "submitted_image_id": id,
            "default_card_image_id": default_card_image_id,
            "nav_page": "submit",
            "background_image_id": default_card_image_id,
            "background_image_width": Constants.get_background_width(),
        },
    )


@view_router.get(
    "/{image_id}",
    summary="Returns the page for the image associated with the specified ID",
    response_class=HTMLResponse,
)
async def page_get_image(request: Request, image_id: str):
    return get_image_page_response(request, image_id, is_direct_request=True)


@api_router.get(
    "/img/random", summary="Returns a random image", response_class=FileResponse
)
async def api_get_rand_image(
    width: Union[int, None] = None,
    height: Union[int, None] = None,
    download: bool = False,
) -> FileResponse:
    image_id = cache.get_random_id()
    return get_file_response(
        image_id=image_id,
        width=width,
        height=height,
        download=download,
        set_cache_header=False,
    )


@api_router.get(
    "/img/{image_id}",
    summary="Returns the image associated with the specified ID",
    response_class=FileResponse,
)
async def api_get_image(
    image_id: str,
    width: Union[int, None] = None,
    height: Union[int, None] = None,
    download: bool = False,
    square: bool = False,
):
    if image_id.endswith(f".{Constants.DEFAULT_EXTENSION}"):
        image_id = image_id.rstrip(f".{Constants.DEFAULT_EXTENSION}")

    return get_file_response(
        image_id=image_id,
        width=width,
        height=height,
        download=download,
        square=square,
    )


@api_router.get(
    "/img",
    summary="Returns a model containing a page of image IDs starting at the specified offset",
)
async def api_get_image_ids_paged(
    offset: int = 0,
    page_size: int = API_PAGE_SIZE_LIMIT,
) -> ImagePageResponse:
    if page_size > API_PAGE_SIZE_LIMIT:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Page size can't be bigger than {API_PAGE_SIZE_LIMIT}!",
        )
    return ImagePageResponse(
        offset=offset, ids=cache.get_ids_paged_with_offset(offset, page_size)
    )


@api_router.get("/health", summary="Returns service health")
async def api_get_health() -> HealthCheckResponse:
    return HealthCheckResponse()


app.include_router(api_router, prefix="/api/v1")
app.include_router(view_router)


@app.exception_handler(HTTPException)
async def http_exception_handler_with_view_handling(request, exc: HTTPException):
    if "view" in request.scope.get("route").tags:
        http_status = HTTPStatus(exc.status_code)
        traceback_str = "\n".join(
            traceback.format_exception(type(exc), value=exc, tb=exc.__traceback__)
        )
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "site_emoji": site_emoji,
                "site_title": site_title,
                "version": version,
                "default_card_image_id": default_card_image_id,
                "http_status": http_status,
                "exception": exc,
                "traceback_str": traceback_str,
                "request": request,
                "background_image_id": default_card_image_id,
                "background_image_width": Constants.get_background_width(),
            },
            status_code=http_status,
        )

    return await http_exception_handler(request, exc)

@app.middleware("http")
async def intercept_requests_on_startup(request: Request, call_next):
    if not cache_start.done():
        path = request.scope.get("path")
        if path.startswith("/api/v1"):
            return JSONResponse(content={"status": "starting"}, status_code=HTTPStatus.SERVICE_UNAVAILABLE)
        if not path.startswith(("/static/dist", "/favicon.ico")):
            return templates.TemplateResponse(
                request=request,
                name="startup.html",
                context={
                    "site_emoji": site_emoji,
                    "site_title": site_title,
                    "version": version,
                    "request": request,
                    "url": str(request.url),
                },
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            )

    return await call_next(request)
