from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MULTIPART_OVERHEAD_BYTES = 64 * 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PROGIMAGE_", env_file=".env", extra="ignore")

    # Which ImageStorage implementation to inject. See get_storage in app/images/api/dependencies.py.
    storage_backend: Literal["local", "s3"] = "local"
    storage_dir: Path = Path("./local_storage")  # used by the "local" backend

    # Upload limits. max_upload_bytes is enforced twice: on the raw request body by MaxBodySizeMiddleware (before
    # multipart parsing spools anything) and on the image bytes by ImageValidator.
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_image_pixels: int = Field(default=40_000_000, gt=0)  # width x height, read from the header

    # PostgreSQL system of record for image metadata (SQLAlchemy URL, psycopg 3 driver). Required, no default.
    # e.g. postgresql+psycopg://progimage:progimage@localhost:5433/progimage  (see docker-compose.yml)
    database_url: str

    # "s3" backend settings. Placeholders only for now; the S3 backend is not wired to a real bucket.
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None  # e.g. localstack / minio
    s3_prefix: str = ""
    aws_access_key_id: str | None = None
    aws_secret_access_key: SecretStr | None = None

    # TEMPORARY: a single shared credential pair for HTTP Basic auth, good enough for this assessment only.
    # A real rollout would depend on who the caller is: end users via OIDC/OAuth2 login (JWT sessions),
    # machine-to-machine via OAuth2 client credentials / API keys / mTLS, with per-caller identity and scopes.
    # Required (no default) so the app fails fast rather than running with a guessable password.
    auth_username: str
    auth_password: SecretStr

    @property
    def max_request_bytes(self) -> int:
        """Body limit for the whole HTTP request: the image plus headroom for multipart boundaries and headers."""
        return self.max_upload_bytes + _MULTIPART_OVERHEAD_BYTES

    @model_validator(mode="after")
    def _require_bucket_for_s3(self) -> Self:
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("PROGIMAGE_S3_BUCKET is required when PROGIMAGE_STORAGE_BACKEND=s3")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
