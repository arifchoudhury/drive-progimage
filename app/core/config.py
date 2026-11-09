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

    # PostgreSQL metadata store (SQLAlchemy URL, psycopg 3 driver). Required.
    database_url: str

    # "s3" backend settings. Only tested against a fake client so far.
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_prefix: str = ""
    aws_access_key_id: str | None = None
    aws_secret_access_key: SecretStr | None = None

    # App-level rate limiting (app/core/rate_limit), per client IP over a 60-second window. Coarse flood protection
    # belongs at the gateway; this is the per-endpoint quota. "memory" counts per process, so any deployment with
    # more than one worker or replica needs "redis" for one shared count.
    rate_limit_enabled: bool = True
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    redis_url: str | None = None
    rate_limit_write_per_minute: int = Field(default=30, gt=0)  # uploads: decoding and storing is the costly path
    rate_limit_read_per_minute: int = Field(default=600, gt=0)

    # TEMPORARY shared Basic-auth credential (see app/core/auth.py). Required, so the app fails fast without it.
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

    @model_validator(mode="after")
    def _require_url_for_redis(self) -> Self:
        if self.rate_limit_backend == "redis" and not self.redis_url:
            raise ValueError("PROGIMAGE_REDIS_URL is required when PROGIMAGE_RATE_LIMIT_BACKEND=redis")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
