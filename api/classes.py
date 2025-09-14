from dataclasses import dataclass
from typing import Union
from fastapi.responses import Response
from PIL import Image

from .utils import FilenameUtils


@dataclass
class ImageMetadata:
    original_width: int
    original_height: int
    media_type: str
    format: str

    def get_filename(
        self, id: str, scaled_width: Union[int, None], scaled_height: Union[int, None]
    ) -> str:
        width = self.original_width if not scaled_width else scaled_width
        height = self.original_height if not scaled_height else scaled_height

        return FilenameUtils.get_filename(
            id=id, width=width, height=height, format=self.format
        )

    @staticmethod
    def from_image(image: Image.Image) -> "ImageMetadata":
        return ImageMetadata(
            original_width=image.width,
            original_height=image.height,
            media_type=Image.MIME.get(image.format.upper()),
            format=image.format,
        )

@dataclass
class TemplateResolutionMetadata:
    current_width: int
    current_height: int
    variant_ladder: list["ResolutionVariant"]

@dataclass
class ResolutionVariant:
    width: int
    height: int
    current: bool
    filename: str

class FaviconResponse(Response):
    media_type = "image/svg+xml"
