"""Docker container lifecycle manager for CosyVoice server."""

from __future__ import annotations

import atexit
import logging
import subprocess
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_IMAGE = "tank-cosyvoice:latest"
DEFAULT_CONTAINER = "tank-cosyvoice"
DEFAULT_PORT = 50000
DEFAULT_MODEL_DIR = "iic/CosyVoice-300M-SFT"
HEALTH_TIMEOUT_S = 300
HEALTH_POLL_INTERVAL_S = 3.0
DOCKER_CMD = "docker"


class CosyVoiceServerError(RuntimeError):
    """Raised when Docker operations fail."""


class CosyVoiceServer:
    """Manages a CosyVoice Docker container.

    Builds the image (if missing), starts the container, waits for it to
    become healthy, and registers an ``atexit`` hook to stop it on shutdown.
    """

    def __init__(self, config: dict) -> None:
        self._image = config.get("docker_image", DEFAULT_IMAGE)
        self._container = config.get("docker_container", DEFAULT_CONTAINER)
        self._port = int(config.get("port", DEFAULT_PORT))
        self._model_dir = config.get("model_dir", DEFAULT_MODEL_DIR)
        self._health_timeout = float(
            config.get("docker_health_timeout", HEALTH_TIMEOUT_S)
        )
        self._stopped = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ensure_running(self) -> str:
        """Start the container if not already running. Return ``base_url``."""
        if self._is_container_running():
            logger.info("CosyVoice container '%s' already running", self._container)
            return self._base_url()

        if not self._image_exists():
            self._build_image()

        self._start_container()
        self._wait_healthy()
        atexit.register(self.stop)
        return self._base_url()

    def stop(self) -> None:
        """Stop and remove the container (idempotent)."""
        if self._stopped:
            return
        self._stopped = True
        logger.info("Stopping CosyVoice container '%s'", self._container)
        _run_docker(["stop", self._container], check=False)
        _run_docker(["rm", "-f", self._container], check=False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _base_url(self) -> str:
        return f"http://localhost:{self._port}"

    def _image_exists(self) -> bool:
        result = _run_docker(
            ["image", "inspect", self._image],
            check=False,
            capture=True,
        )
        return result.returncode == 0

    def _is_container_running(self) -> bool:
        result = _run_docker(
            ["inspect", "-f", "{{.State.Running}}", self._container],
            check=False,
            capture=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _build_image(self) -> None:
        dockerfile_dir = Path(__file__).resolve().parent.parent / "docker"
        logger.info(
            "Building CosyVoice Docker image '%s' (this may take a while)…",
            self._image,
        )
        _run_docker(
            [
                "build",
                "-t", self._image,
                "--build-arg", f"MODEL_DIR={self._model_dir}",
                str(dockerfile_dir),
            ],
            check=True,
        )
        logger.info("Docker image '%s' built successfully", self._image)

    def _start_container(self) -> None:
        # Remove stale container with the same name (stopped but not removed)
        _run_docker(["rm", "-f", self._container], check=False, capture=True)

        logger.info(
            "Starting CosyVoice container '%s' on port %d",
            self._container,
            self._port,
        )
        _run_docker(
            [
                "run", "-d",
                "--name", self._container,
                "-p", f"{self._port}:{DEFAULT_PORT}",
                self._image,
            ],
            check=True,
        )

    def _wait_healthy(self) -> None:
        """Poll the server until it responds or timeout is reached."""
        deadline = time.monotonic() + self._health_timeout
        logger.info(
            "Waiting for CosyVoice server at %s (timeout=%ds)…",
            self._base_url(),
            int(self._health_timeout),
        )

        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                resp = httpx.get(f"{self._base_url()}/docs", timeout=5.0)
                if resp.status_code < 500:
                    logger.info("CosyVoice server is healthy")
                    return
            except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException) as exc:
                last_error = exc
            time.sleep(HEALTH_POLL_INTERVAL_S)

        self.stop()
        raise CosyVoiceServerError(
            f"CosyVoice server did not become healthy within "
            f"{int(self._health_timeout)}s. Last error: {last_error}"
        )


def _run_docker(
    args: list[str],
    *,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a ``docker`` CLI command."""
    cmd = [DOCKER_CMD, *args]
    logger.debug("Running: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
    )
