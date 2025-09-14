import base64
import hashlib
from io import BytesIO
import math
import os
from typing import Callable, Union
from PIL import Image, ImageOps

from ..classes import ImageMetadata
from .filename import FilenameUtils
from ..constants import Constants

MAX_SIZE = Constants.get_max_width()
FORMAT = Constants.DEFAULT_FORMAT


class ImageUtils:
    def __init__(self):
        pass

    @staticmethod
    def resize(
        image: Image.Image,
        width: Union[int, None] = None,
        height: Union[int, None] = None,
        copy: bool = True,
    ) -> Image.Image:
        if not width and not height:
            return image  # nothing to do

        if not width and height:
            width = height
        elif width and not height:
            height = width

        new_image = image

        if copy:
            new_image = image.copy()

        new_image.thumbnail((width, height))
        new_image.format = image.format

        return new_image

    @staticmethod
    def calculate_scaled_size(
        original_width: int,
        original_height: int,
        width: Union[int, None] = None,
        height: Union[int, None] = None,
    ) -> tuple[int, int]:
        if not width and not height:
            return original_width, original_height  # nothing to do

        # doing my own math, none of this convoluted pillow stuff
        aspect_ratio = original_width / original_height

        if not width:
            width = int(height * aspect_ratio)

        if not height:
            height = int(width / aspect_ratio)

        return width, height

    @staticmethod
    def convert_to_unified_format_in_buffer(image: Image.Image) -> Image.Image:
        """
        Generates a new image from an input image with the following properties:
        - RGB color palette (no alpha channel)
        - PNG format
        - Maximum size: 2048 x 2048
        - no EXIF data from the input image

        Args:
            image (PIL.Image.Image): the image to convert

        Returns:
            PIL.Image.Image: the converted image
        """
        rgb_image = image.convert("RGB")

        max_size = MAX_SIZE

        if rgb_image.width > max_size or rgb_image.height > max_size:
            rgb_image = ImageUtils.resize(rgb_image, max_size, max_size, copy=False)

        buf = BytesIO()
        rgb_image.save(buf, format=FORMAT)
        buf.seek(0)
        new_image = Image.open(buf)
        return new_image

    @staticmethod
    def convert_to_unified_format_and_write_to_filesystem(
        output_path: str, image: Image.Image, force_write: bool = False
    ) -> tuple[str, ImageMetadata]:
        """
        Generates a new image from an input image with the following properties:
        - RGB color palette (no alpha channel)
        - PNG format
        - Maximum size: 2048 x 2048
        - no EXIF data from the input image

        Args:
            output_path (str): the path to write the image to (filename will be appended)
            image (PIL.Image.Image): the image to convert
        """

        rgb_image = image.convert("RGB")
        ImageOps.exif_transpose(rgb_image, in_place=True)

        max_size = MAX_SIZE

        if rgb_image.width > max_size or rgb_image.height > max_size:
            rgb_image = ImageUtils.resize(rgb_image, max_size, max_size, copy=False)

        os.makedirs(output_path, exist_ok=True)

        id = ImageUtils.get_id(data=rgb_image)
        filename = os.path.join(
            output_path,
            FilenameUtils.get_filename(
                id=id, width=rgb_image.width, height=rgb_image.height, format=FORMAT
            ),
        )

        if force_write or not os.path.isfile(filename):
            rgb_image.save(filename, format=FORMAT)

        metadata = ImageMetadata(
            original_width=rgb_image.width,
            original_height=rgb_image.height,
            media_type=Image.MIME.get(FORMAT.upper()),
            format=FORMAT,
        )

        return (id, metadata)

    @staticmethod
    def write_scaled_copy_from_source_filename_to_filesystem(
        *,
        id: str,
        source_filename: str,
        output_path: str,
        width: Union[int, None] = None,
        height: Union[int, None] = None,
        crop: bool = False,
    ) -> str:
        source = Image.open(source_filename)
        return ImageUtils.write_scaled_copy_to_filesystem(
            id=id,
            source=source,
            output_path=output_path,
            width=width,
            height=height,
            crop=crop,
        )

    @staticmethod
    def write_scaled_copy_to_filesystem(
        *,
        id: str,
        source: Image.Image,
        output_path: str,
        width: Union[int, None] = None,
        height: Union[int, None] = None,
        crop: bool = False,
    ) -> str:
        image = source
        if crop:
            image = ImageUtils._crop_center(source, min(source.size), min(source.size))

        image = ImageUtils.resize(image, width, height, copy=False)
        image.format = source.format
        filename = os.path.join(
            output_path,
            FilenameUtils.get_filename(
                id=id, width=width, height=height, format=image.format
            ),
        )
        image.save(filename)
        return filename

    @staticmethod
    def get_id(*, data: Image.Image) -> str:
        pixel_bytes = data.tobytes()
        hash_input = f"{data.width}_{data.height}".encode("utf-8") + pixel_bytes
        digest = hashlib.sha256(hash_input).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    @staticmethod
    # https://note.nkmk.me/en/python-pillow-square-circle-thumbnail/
    # Thanks!
    def _crop_center(source: Image.Image, crop_width: int, crop_height: int):
        img_width, img_height = source.size
        return source.crop(
            (
                (img_width - crop_width) // 2,
                (img_height - crop_height) // 2,
                (img_width + crop_width) // 2,
                (img_height + crop_height) // 2,
            )
        )
