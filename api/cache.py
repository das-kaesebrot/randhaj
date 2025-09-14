import logging
import os
import random
from threading import Thread, Lock
import inotify.adapters
import inotify.constants
from PIL import Image
from typing import Dict, Union

from .constants import Constants
from .decorators import wait_lock
from .classes import ImageMetadata
from .utils import FilenameUtils, ImageUtils, GeneralUtils, ThreadingUtils

from datetime import timedelta
from time import perf_counter


class Cache:
    _ids_to_metadata: Dict[str, ImageMetadata] = {}
    _image_dir: str
    _cache_dir: str
    _logger: logging.Logger
    
    _inotify_thread: Thread
    _original_filenames_to_ids: Dict[str, str] = {}
    _mutex_lock: Lock = Lock()

    def __init__(self, *, image_dir: str, cache_dir: str, enable_inotify: bool = True):
        image_dir = os.path.abspath(image_dir)
        cache_dir = os.path.abspath(cache_dir)
        
        self._logger = logging.getLogger(__name__)
        self._logger.info(f"Created cache instance with image directory='{image_dir}' and cache directory='{cache_dir}'")
        self._cache_dir = cache_dir
        self._image_dir = image_dir
        
        self._generate_cache()
        
        if enable_inotify: self._dispatch_inotify_thread()

    def _generate_cache(self) -> Dict[str, ImageMetadata]:
        start = perf_counter()
        image_dir = self._image_dir
        
        filename_to_image: dict[str, Image.Image] = {}

        for filename in os.listdir(image_dir):
            if not os.path.splitext(filename.lower())[1] in Constants.ALLOWED_INPUT_FILE_EXTENSIONS:
                self._logger.warning(f"Ignoring file '{filename}' because it doesn't have an allowed file extension")
                continue
            
            try:
                img = Image.open(os.path.join(image_dir, filename))
                img.load()
                filename_to_image[filename] = img
            except OSError as e:
                self._logger.exception(f"Failed loading file '{os.path.join(image_dir, filename)}'")
                continue

        for filename, image in filename_to_image.items():
            try:
                id, metadata = ImageUtils.convert_to_unified_format_and_write_to_filesystem(
                    output_path=self._cache_dir, image=image
                )
                self._ids_to_metadata[id] = metadata
                self._original_filenames_to_ids[filename] = id
                image.close()
            except OSError:
                self._logger.exception(f"Failed writing converted file '{'no filename' if not image.filename else image.filename}'")
                continue

        end = perf_counter()
        self._logger.info(f"Generated {len(self._ids_to_metadata.keys())} cached images in {timedelta(seconds=end-start)}")
    
    def _dispatch_inotify_thread(self):
        self._logger.info("Dispatching inotify thread")
        
        self._inotify_thread = Thread(target=self._watch_fs_events)
        self._inotify_thread.start()
    
    def _watch_fs_events(self):
        logger = logging.getLogger(f"{__name__}.inotify-thread")
        try:            
            i = inotify.adapters.Inotify()

            i.add_watch(self._image_dir, mask=inotify.constants.IN_DELETE | inotify.constants.IN_CLOSE_WRITE)
            logger.info(f"Added watch for folder '{self._image_dir}'")

            for event in i.event_gen(yield_nones=False):
                (event_obj, _, _, filename) = event
                logger.debug(event)                
                mask = event_obj.mask
                                
                if (mask & inotify.constants.IN_CLOSE_WRITE) == inotify.constants.IN_CLOSE_WRITE:
                    logger.info(f"Detected new file '{filename}', adjusting cache")
                    
                    if not os.path.splitext(filename.lower())[1] in Constants.ALLOWED_INPUT_FILE_EXTENSIONS:
                        logger.warning(f"Ignoring file '{filename}' because it doesn't have an allowed file extension")
                        continue
                    
                    image: Image.Image = None
                    try:
                        image = Image.open(os.path.join(self._image_dir, filename))
                    except OSError as e:
                        logger.exception("Exception while opening file")
                        continue
                    
                    ThreadingUtils.wait_and_acquire_lock(self._mutex_lock)
                    try:
                        id, metadata = ImageUtils.convert_to_unified_format_and_write_to_filesystem(
                            output_path=self._cache_dir, image=image
                        )
                        self._ids_to_metadata[id] = metadata
                        self._original_filenames_to_ids[filename] = id
                    except OSError as e:
                        logger.exception("Exception while converting file")
                        continue
                    finally:
                        self._mutex_lock.release()
                        if image: image.close()

                elif (mask & inotify.constants.IN_DELETE) == inotify.constants.IN_DELETE:
                    logger.info(f"Detected deleted file '{filename}', adjusting cache")
                    ThreadingUtils.wait_and_acquire_lock(self._mutex_lock)
                    id = self._original_filenames_to_ids.get(filename)
                    if id:
                        del self._original_filenames_to_ids[filename]
                        del self._ids_to_metadata[id]
                    self._mutex_lock.release()
                    
        except KeyboardInterrupt or InterruptedError as e:
            logger.info(f"{type(e).__name__} received. Stopping thread.")
        finally:
            if self._mutex_lock.locked(): self._mutex_lock.release()

    def get_filename(
        self, id: str, width: Union[int, None] = None, height: Union[int, None] = None, crop: bool = False, generate_variant_if_missing: bool = True,
    ) -> str:
        ThreadingUtils.wait_and_acquire_lock(self._mutex_lock)
        metadata = self._ids_to_metadata.get(id)
        self._mutex_lock.release()

        width, height = GeneralUtils.clamp(width, 0, metadata.original_width), GeneralUtils.clamp(
            height, 0, metadata.original_height
        )
        
        if not crop:
            width, height = ImageUtils.calculate_scaled_size(
                metadata.original_width,
                metadata.original_height,
                width=width,
                height=height,
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
        filename = ImageUtils.write_scaled_copy_from_source_filename_to_filesystem(
            id=id,
            source_filename=source_filename,
            output_path=self._cache_dir,
            width=width,
            height=height,
            crop=crop,
        )
        
        return filename
    
    @wait_lock(_mutex_lock)
    def get_random_id(self) -> str:
        return random.choice(list(self._ids_to_metadata.keys()))

    @wait_lock(_mutex_lock)
    def get_random(self) -> tuple[str, ImageMetadata]:
        return random.choice(list(self._ids_to_metadata.values()))

    @wait_lock(_mutex_lock)
    def get_metadata(self, id: str) -> Union[ImageMetadata, None]:
        return self._ids_to_metadata.get(id)
    
    @wait_lock(_mutex_lock)
    def id_exists(self, id: str) -> bool:
        return id in self._ids_to_metadata.keys()
    
    @wait_lock(_mutex_lock)
    def get_first_id(self) -> dict[str, ImageMetadata]:
        return sorted(self._ids_to_metadata.keys())[0]
