import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import Settings, get_settings

basic_scheme = HTTPBasic()


def require_auth(
    credentials: Annotated[HTTPBasicCredentials, Depends(basic_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """TEMPORARY auth: one shared username/password checked on every request (HTTP Basic).

    Not a long-term design. A proper solution depends on who the caller is (end users: OIDC/OAuth2 + JWT;
    machine-to-machine: OAuth2 client credentials, API keys or mTLS) and would carry a per-caller identity.
    """
    # Compare both fields without short-circuiting, in constant time.
    username_ok = secrets.compare_digest(credentials.username.encode(), settings.auth_username.encode())
    password_ok = secrets.compare_digest(
        credentials.password.encode(), settings.auth_password.get_secret_value().encode()
    )
    if not (username_ok and password_ok):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
