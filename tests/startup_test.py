import os
import sys
import tempfile
import time

import pytest
from PIL import Image
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    with tempfile.TemporaryDirectory() as image_dir:
        with tempfile.TemporaryDirectory() as cache_dir:
            image_path = os.path.join(image_dir, "test.png")
            Image.new("RGB", (4000, 3000), color="red").save(image_path)

            env_overrides = {
                "RANDHAJ_IMAGE_DIR": image_dir,
                "RANDHAJ_CACHE_DIR": cache_dir,
                "RANDHAJ_CACHE_DB_FILE": os.path.join(cache_dir, ".test-cache.db"),
                "RANDHAJ_SUBMISSIONS_DIR": os.path.join(cache_dir, "submissions"),
                "RANDHAJ_SITE_TITLE": "Test App",
                "RANDHAJ_SITE_EMOJI": "\U0001f52c",
                "RANDHAJ_LOG_LEVEL": "CRITICAL",
            }
            saved = {}
            for k, v in env_overrides.items():
                saved[k] = os.environ.get(k)
                os.environ[k] = v

            sys.modules.pop("main", None)
            import main

            yield main.app

            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def _wait_for_cache(timeout: float = 5.0) -> bool:
    import main

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        cache_start = main.cache_start
        if cache_start is not None and cache_start.done():
            exc = cache_start.exception()
            if exc is not None:
                raise RuntimeError("Cache startup failed") from exc
            return True
        time.sleep(0.05)
    return False


class TestAppStartup:
    def test_health_endpoint(self, app):
        with TestClient(app) as client:
            assert _wait_for_cache()
            response = client.get("/api/v1/health")
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"

    def test_image_is_cached_after_startup(self, app):
        with TestClient(app) as client:
            assert _wait_for_cache()
            import main

            assert main.cache.get_total_image_count() == 1

    def test_random_image_endpoint(self, app):
        with TestClient(app) as client:
            assert _wait_for_cache()
            response = client.get("/api/v1/img/random")
            assert response.status_code == 200
            assert response.headers["content-type"] == "image/jpeg"

    def test_root_page(self, app):
        with TestClient(app) as client:
            assert _wait_for_cache()
            response = client.get("/")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    def test_gallery_page(self, app):
        with TestClient(app) as client:
            assert _wait_for_cache()
            response = client.get("/gallery")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
