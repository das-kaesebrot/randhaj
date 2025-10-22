from dataclasses import dataclass
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles


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


# https://stackoverflow.com/a/77823873
class StaticFilesCustomHeaders(StaticFiles):
    def __init__(
        self,
        *args,
        headers={
            "Cache-Control": "public, max-age=31536000, s-maxage=31536000, immutable"
        },
        **kwargs,
    ):
        self.__default_headers = headers
        super().__init__(*args, **kwargs)

    def file_response(self, *args, **kwargs) -> Response:
        resp: Response = super().file_response(*args, **kwargs)

        for header, value in self.__default_headers.items():
            resp.headers.setdefault(header, value)

        return resp
