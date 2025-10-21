from dataclasses import dataclass
from fastapi.responses import Response


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
