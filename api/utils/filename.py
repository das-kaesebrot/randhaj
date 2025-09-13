from PIL import Image


class FilenameUtils:
    def __init__(self):
        pass

    @staticmethod
    def get_filename_with_image_data(*, id: str, data: Image.Image):
        return FilenameUtils.get_filename(
            id=id, width=data.width, height=data.height, format=data.format
        )

    @staticmethod
    def get_filename(*, id: str, width: int, height: int, format: str):
        return f"{id}_{width}x{height}.{format.lower()}"
