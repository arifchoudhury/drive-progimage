import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx2
import pytest

STARTUP_TIMEOUT_SECONDS = 15
USERNAME = "e2e-user"
PASSWORD = "e2e-password"
MAX_UPLOAD_BYTES = 64 * 1024  # small, so the size-limit test doesn't need to send megabytes


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def base_url(tmp_path_factory: pytest.TempPathFactory, database_url: str) -> Iterator[str]:
    """Run the real app under uvicorn with a throwaway storage dir and the migrated test DB; no overrides."""
    storage_dir: Path = tmp_path_factory.mktemp("e2e-storage")
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "PROGIMAGE_STORAGE_DIR": str(storage_dir),
        "PROGIMAGE_DATABASE_URL": database_url,
        "PROGIMAGE_AUTH_USERNAME": USERNAME,
        "PROGIMAGE_AUTH_PASSWORD": PASSWORD,
        "PROGIMAGE_MAX_UPLOAD_BYTES": str(MAX_UPLOAD_BYTES),
    }
    log = tmp_path_factory.mktemp("e2e-logs") / "uvicorn.log"

    with log.open("wb") as log_file:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "--factory", "app.main:create_app", "--port", str(port)],
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    pytest.fail(f"uvicorn exited early:\n{log.read_text()}")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                pytest.fail(f"uvicorn not ready after {STARTUP_TIMEOUT_SECONDS}s:\n{log.read_text()}")
            yield url
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


@pytest.fixture
def anonymous_http(base_url: str) -> Iterator[httpx2.Client]:
    with httpx2.Client(base_url=base_url) as c:
        yield c


@pytest.fixture
def http(base_url: str) -> Iterator[httpx2.Client]:
    with httpx2.Client(base_url=base_url, auth=(USERNAME, PASSWORD)) as c:
        yield c
