import logging
import os
from typing import Union
import crawleruseragents
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from kaesebrot_commons.logging.utils import LoggingUtils

from api.cache import Cache
from api.classes import FaviconResponse, ResolutionVariant, TemplateResolutionMetadata
from api.utils.image import ImageProcessor
from api.constants import Constants

ENV_PREFIX = "RANDHAJ"

version = os.getenv("APP_VERSION", "local-dev")
source_image_dir = os.getenv(f"{ENV_PREFIX}_IMAGE_DIR", "assets/images")
cache_dir = os.getenv(f"{ENV_PREFIX}_CACHE_DIR", "cache")
site_title = os.getenv(f"{ENV_PREFIX}_SITE_TITLE", "Random image")
site_emoji = os.getenv(f"{ENV_PREFIX}_SITE_EMOJI", "🦈")
default_card_image_id = os.getenv(f"{ENV_PREFIX}_DEFAULT_CARD_IMAGE")
loglevel = os.getenv(
    f"{ENV_PREFIX}_LOG_LEVEL", os.getenv("UVICORN_LOG_LEVEL", logging.INFO)
)

LoggingUtils.setup_logging_with_default_formatter(loglevel=loglevel)

for name in logging.root.manager.loggerDict.keys():
    logging.getLogger(name).handlers = []
    logging.getLogger(name).propagate = True


app = FastAPI(title=site_title)
app.mount("/static", StaticFiles(directory="resources/static"), name="static")
templates = Jinja2Templates(directory="resources/templates")

cache = Cache(image_dir=source_image_dir, cache_dir=cache_dir)

if not default_card_image_id:
    default_card_image_id = cache.get_first_id()


def get_file_response(
    *,
    image_id: str,
    width: Union[int, None] = None,
    height: Union[int, None] = None,
    download: bool = False,
    set_cache_header: bool = True,
    is_thumbnail: bool = False,
) -> FileResponse:
    if not cache.id_exists(image_id):
        raise HTTPException(
            status_code=404, detail=f"File with id='{image_id}' could not be found!"
        )

    metadata = cache.get_metadata(image_id)

    if is_thumbnail:
        width, height = (
            Constants.get_small_thumbnail_width(),
            Constants.get_small_thumbnail_width(),
        )

    if not height and width and width not in Constants.ALLOWED_DIMENSIONS:
        _, height = ImageProcessor.calculate_scaled_size(
            original_width=metadata.original_width,
            original_height=metadata.original_height,
            width=width,
        )
        if not height in Constants.ALLOWED_DIMENSIONS:
            raise HTTPException(
                status_code=400, detail=f"Width is not of allowed value!"
            )

    if not width and height and height not in Constants.ALLOWED_DIMENSIONS:
        width, _ = ImageProcessor.calculate_scaled_size(
            original_width=metadata.original_width,
            original_height=metadata.original_height,
            height=height,
        )

        if not width in Constants.ALLOWED_DIMENSIONS:
            raise HTTPException(
                status_code=400, detail=f"Height is not of allowed value!"
            )

    filename = cache.get_filename(
        image_id, width=width, height=height, crop=is_thumbnail
    )

    headers = {
        "Content-Disposition": (
            "inline"
            if not download
            else f'attachment; filename="{os.path.basename(filename)}"'
        ),
        "X-Image-Id": f"{image_id}",
    }

    if set_cache_header:
        headers["Cache-Control"] = "max-age=2592000, public, no-transform"

    return FileResponse(
        path=filename,
        media_type=metadata.media_type,
        headers=headers,
    )


def get_image_page_response(
    request: Request, image_id: str, is_direct_request: bool = False
) -> HTMLResponse:
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
                crop=False,
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
        },
    )


@app.get("/favicon.ico", response_class=FaviconResponse)
async def get_favicon():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        + f'<text y=".9em" font-size="90">{site_emoji}</text>'
        + "</svg>"
    )


@app.get("/", response_class=Union[HTMLResponse, RedirectResponse])
async def page_redirect_rand_image(request: Request, redirect: bool = False):
    image_id = cache.get_random_id()

    if redirect:
        return RedirectResponse(request.url_for("page_get_image", image_id=image_id))

    return get_image_page_response(request, image_id)


@app.get("/{image_id}", response_class=HTMLResponse)
async def page_get_image(request: Request, image_id: str):
    return get_image_page_response(request, image_id, is_direct_request=True)


@app.get("/api/img/{image_id}")
async def api_get_image(
    image_id: str,
    width: Union[int, None] = None,
    height: Union[int, None] = None,
    download: bool = False,
    thumb: bool = False,
):
    if image_id.endswith(f".{Constants.DEFAULT_FORMAT}"):
        image_id = image_id.rstrip(f".{Constants.DEFAULT_FORMAT}")

    return get_file_response(
        image_id=image_id,
        width=width,
        height=height,
        download=download,
        is_thumbnail=thumb,
    )


@app.get("/api/img")
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
