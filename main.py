import logging
import os
import time
from typing import Union
import crawleruseragents
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from kaesebrot_commons.logging.utils import LoggingUtils

from api.cache import Cache
from api.classes import (
    FaviconResponse,
    ResolutionVariant,
    StaticFilesCustomHeaders,
    TemplateResolutionMetadata,
)
from api.utils.image import ImageProcessor
from api.constants import Constants

ENV_PREFIX = "RANDHAJ"

STATIC_EXTERNAL_CACHING_TIME = 365 * 24 * 60 * 60  # 365 days in seconds
IMAGE_FILES_CACHING_TIME = 30 * 24 * 60 * 60  # 30 days in seconds

version = os.getenv("APP_VERSION", "local-dev")
source_image_dir = os.getenv(f"{ENV_PREFIX}_IMAGE_DIR", "assets/images")
cache_dir = os.getenv(f"{ENV_PREFIX}_CACHE_DIR", "cache")
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


app = FastAPI(title=site_title, version=version)
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
)

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
            status_code=404, detail=f"File with id='{image_id}' could not be found!"
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
                status_code=400, detail="Width is not of allowed value!"
            )

    if not width and height and height not in Constants.ALLOWED_DIMENSIONS:
        width, _ = ImageProcessor.calculate_scaled_size(
            original_width=metadata.original_width,
            original_height=metadata.original_height,
            height=height,
        )

        if width not in Constants.ALLOWED_DIMENSIONS:
            raise HTTPException(
                status_code=400, detail="Height is not of allowed value!"
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
            status_code=404, detail=f"Image with id='{image_id}' could not be found!"
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
                generate_variant_if_missing=False,
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
        },
    )


def get_gallery_page_response(
    request: Request,
    page: int = 1,
    page_size=50,
) -> HTMLResponse:
    start = time.perf_counter_ns()
    if page < 1:
        raise HTTPException(status_code=400, detail="Page can't be smaller than 1!")

    if page_size > 50:
        raise HTTPException(
            status_code=400, detail="Page size can't be bigger than 50!"
        )

    page_max = (cache.get_total_image_count() // page_size) + 1
    if page > page_max:
        raise HTTPException(
            status_code=400, detail=f"Page can't be bigger than {page_max}!"
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
        },
    )


@view_router.get("/favicon.ico", response_class=FaviconResponse)
async def get_favicon():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        + f'<text y=".9em" font-size="90">{site_emoji}</text>'
        + "</svg>"
    )


@view_router.get("/", response_class=HTMLResponse)
async def page_redirect_rand_image(request: Request):
    image_id = cache.get_random_id()
    return get_image_page_response(request, image_id)


@view_router.get("/gallery", response_class=HTMLResponse)
async def page_get_gallery(request: Request, page: int = 1, page_size: int = 50):
    return get_gallery_page_response(request, page, page_size)


@view_router.get("/{image_id}", response_class=HTMLResponse)
async def page_get_image(request: Request, image_id: str):
    return get_image_page_response(request, image_id, is_direct_request=True)


@api_router.get("/img/{image_id}")
async def api_get_image(
    image_id: str,
    width: Union[int, None] = None,
    height: Union[int, None] = None,
    download: bool = False,
    square: bool = False,
):
    if image_id.endswith(f".{Constants.DEFAULT_FORMAT}"):
        image_id = image_id.rstrip(f".{Constants.DEFAULT_FORMAT}")

    return get_file_response(
        image_id=image_id,
        width=width,
        height=height,
        download=download,
        square=square,
    )


@api_router.get("/img")
async def api_get_rand_image(
    width: Union[int, None] = None,
    height: Union[int, None] = None,
    download: bool = False,
):
    image_id = cache.get_random_id()
    return get_file_response(
        image_id=image_id,
        width=width,
        height=height,
        download=download,
        set_cache_header=False,
    )


app.include_router(api_router, prefix="/api/v1")
app.include_router(view_router)
