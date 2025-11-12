from concurrent.futures import ThreadPoolExecutor
import logging
import os
from threading import Thread
import inotify.adapters
import inotify.constants
from PIL import Image
from typing import Union
from sqlalchemy import Engine, create_engine, delete, func, select
from sqlalchemy.orm import Session

from api.constants import Constants
from api.models import Base, CachedImage, ImageMetadata
from api.utils.filename import FilenameUtils
from api.utils.general import GeneralUtils
from api.utils.image import ImageProcessor

from datetime import timedelta
from time import perf_counter


class Cache:
    _image_dir: str
    _cache_dir: str
    _logger: logging.Logger

    _inotify_thread: Thread

    __engine: Engine = None
    __session = None

    def __init__(
        self,
        *,
        image_dir: str,
        cache_dir: str,
        enable_inotify: bool = True,
        max_initial_cache_generator_workers: int = 4,
        connection_string: str = "sqlite:///",
    ):
        image_dir = os.path.abspath(image_dir)
        cache_dir = os.path.abspath(cache_dir)

        self._logger = logging.getLogger(__name__)
        self._logger.info(
            f"Created cache instance with image directory='{image_dir}' and cache directory='{cache_dir}'"
        )
        self._cache_dir = cache_dir
        self._image_dir = image_dir

        self._logger.info(
            f"Creating database engine with connection string '{connection_string}'"
        )

        # only echo SQL statements if we're logging at the debug level
        echo = self._logger.getEffectiveLevel() <= logging.DEBUG

        self.__engine = create_engine(
            connection_string, echo=echo, connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(self.__engine)
        self.__session = Session(self.__engine)

        assert self.__engine is not None
        assert self.__session is not None

        self._generate_cache(max_threadpool_workers=max_initial_cache_generator_workers)

        if enable_inotify:
            self._dispatch_inotify_thread()

    def _generate_cache(self, max_threadpool_workers: int):
        start = perf_counter()

        def convert_and_save(filename: str):
            self._logger.debug(f"Started conversion job for '{filename}'")
            try:
                with Image.open(os.path.join(self._image_dir, filename)) as image:
                    id, metadata = (
                        ImageProcessor.convert_to_unified_format_and_write_to_filesystem(
                            output_path=self._cache_dir, image=image
                        )
                    )
                    cached_image = CachedImage(
                        id=id, original_filename=filename, image_metadata=metadata
                    )
                    self.__session.add(cached_image)
                    self._logger.debug(f"Done converting '{filename}'")
            except OSError:
                self._logger.exception(f"Failed converting '{filename}'")

        with ThreadPoolExecutor(max_workers=max_threadpool_workers) as executor:
            self._logger.info(
                f"Created initial generation threadpool with {executor._max_workers} workers"
            )
            for filename in os.listdir(self._image_dir):
                if (
                    os.path.splitext(filename.lower())[1]
                    not in Constants.ALLOWED_INPUT_FILE_EXTENSIONS
                ):
                    self._logger.warning(
                        f"Ignoring file '{filename}' because it doesn't have an allowed file extension"
                    )
                    continue

                executor.submit(convert_and_save, filename=filename)

        self._commit_and_flush()

        end = perf_counter()
        self._logger.info(
            f"Generated {self.get_total_image_count()} cached images in {timedelta(seconds=end - start)}"
        )

    def _dispatch_inotify_thread(self):
        self._logger.info("Dispatching inotify thread")

        self._inotify_thread = Thread(target=self._watch_fs_events, daemon=True)
        self._inotify_thread.start()

    def _watch_fs_events(self):
        logger = logging.getLogger(f"{__name__}.inotify-thread")
        try:
            i = inotify.adapters.Inotify()

            i.add_watch(
                self._image_dir,
                mask=inotify.constants.IN_DELETE | inotify.constants.IN_CLOSE_WRITE,
            )
            logger.info(f"Added watch for folder '{self._image_dir}'")

            for event in i.event_gen(yield_nones=False):
                (event_obj, _, _, filename) = event
                logger.debug(event)
                mask = event_obj.mask

                if (
                    mask & inotify.constants.IN_CLOSE_WRITE
                ) == inotify.constants.IN_CLOSE_WRITE:
                    logger.info(f"Detected new file '{filename}', adjusting cache")

                    if (
                        os.path.splitext(filename.lower())[1]
                        not in Constants.ALLOWED_INPUT_FILE_EXTENSIONS
                    ):
                        logger.warning(
                            f"Ignoring file '{filename}' because it doesn't have an allowed file extension"
                        )
                        continue

                    image: Image.Image = None
                    try:
                        image = Image.open(os.path.join(self._image_dir, filename))
                    except OSError:
                        logger.exception("Exception while opening file")
                        continue

                    try:
                        id, metadata = (
                            ImageProcessor.convert_to_unified_format_and_write_to_filesystem(
                                output_path=self._cache_dir, image=image
                            )
                        )
                        cached_image = CachedImage(
                            id=id, original_filename=filename, image_metadata=metadata
                        )
                        self.__session.add(cached_image)
                    except OSError:
                        logger.exception("Exception while converting file")
                        continue
                    finally:
                        if image:
                            image.close()

                elif (
                    mask & inotify.constants.IN_DELETE
                ) == inotify.constants.IN_DELETE:
                    logger.info(f"Detected deleted file '{filename}', adjusting cache")
                    self._delete_by_original_filename(filename)

        except KeyboardInterrupt or InterruptedError as e:
            logger.info(f"{type(e).__name__} received. Stopping thread.")

    def get_filename(
        self,
        id: str,
        width: Union[int, None] = None,
        height: Union[int, None] = None,
        square: bool = False,
        generate_variant_if_missing: bool = True,
    ) -> str:
        metadata = self.get_metadata(id=id)
        if not metadata:
            raise ValueError(f"Can't find image by id '{id}'!")

        if square:
            height = width
        else:
            width, height = ImageProcessor.calculate_scaled_size(
                metadata.original_width,
                metadata.original_height,
                width=width,
                height=height,
            )

            width, height = (
                GeneralUtils.clamp(width, 0, metadata.original_width),
                GeneralUtils.clamp(height, 0, metadata.original_height),
            )

        expected_filename = os.path.join(
            self._cache_dir,
            FilenameUtils.get_filename(
                id=id, width=width, height=height, format=metadata.format
            ),
        )

        if os.path.isfile(expected_filename) or not generate_variant_if_missing:
            return expected_filename

        source_filename = os.path.join(
            self._cache_dir,
            FilenameUtils.get_filename(
                id=id,
                width=metadata.original_width,
                height=metadata.original_height,
                format=metadata.format,
            ),
        )
        filename = ImageProcessor.write_scaled_copy_from_source_filename_to_filesystem(
            id=id,
            source_filename=source_filename,
            output_path=self._cache_dir,
            width=width,
            height=height,
            crop_square=square,
        )

        return filename

    def get_random_id(self) -> str:
        select_statement = select(CachedImage.id).order_by(func.random()).limit(1)
        return self.__session.scalars(select_statement).one_or_none()

    def get_metadata(self, id: str) -> Union[ImageMetadata, None]:
        select_statement = select(ImageMetadata).where(ImageMetadata.id.is_(id))
        return self.__session.scalars(select_statement).one_or_none()

    def id_exists(self, id: str) -> bool:
        select_statement = select(CachedImage.id).where(CachedImage.id.is_(id))
        return self.__session.scalars(select_statement).one_or_none() is not None

    def get_first_id(self) -> str:
        select_statement = select(CachedImage.id).order_by(CachedImage.id).limit(1)
        return self.__session.scalars(select_statement).one_or_none()

    def get_all_ids(self) -> list[str]:
        select_statement = select(CachedImage.id)
        return self.__session.scalars(select_statement).all()

    def get_ids_paged(self, page: int = 0, page_size: int = 50) -> list[str]:
        return self.get_ids_paged_with_offset(
            offset=(page * page_size), page_size=page_size
        )

    def get_ids_paged_with_offset(
        self, offset: int = 0, page_size: int = 50
    ) -> list[str]:
        select_statement = (
            select(CachedImage.id)
            .order_by(CachedImage.id)
            .offset(offset)
            .limit(page_size)
        )
        return self.__session.scalars(select_statement).all()

    def get_all_images(self) -> list[CachedImage]:
        select_statement = select(CachedImage)
        return self.__session.scalars(select_statement).all()

    def _delete_by_original_filename(self, original_filename: str):
        delete_statement = delete(CachedImage).where(
            CachedImage.original_filename.is_(original_filename)
        )
        self.__session.execute(delete_statement)
        self._commit_and_flush()

    def _commit_and_flush(self):
        self.__session.commit()
        self.__session.flush()

    def get_total_image_count(self) -> int:
        select_statement = select(func.count()).select_from(CachedImage)
        return self.__session.execute(select_statement).scalar() or 0
