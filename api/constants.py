class Constants:
    ALLOWED_DIMENSIONS = [2048, 1024, 512, 256, 128, 64, 32, 16]
    DEFAULT_FORMAT = "jpeg"
    DEFAULT_EXTENSION = "jpg"
    ALLOWED_INPUT_FILE_EXTENSIONS = [".jpg", ".jpeg", ".png"]

    @staticmethod
    def get_default_width():
        return Constants.ALLOWED_DIMENSIONS[2]

    @staticmethod
    def get_max_width():
        return Constants.ALLOWED_DIMENSIONS[0]

    @staticmethod
    def get_small_thumbnail_width():
        return Constants.ALLOWED_DIMENSIONS[3]
