# zackry_cli/testtool/config.py
#
# Data models for the API testing tool (zackry test).
#
# These describe WHICH APIs and endpoints to test and HOW to authenticate,
# but never hold a real secret: auth fields only store the NAME of an
# environment variable (e.g. "STAGING_API_TOKEN"). The actual token lives
# in .env, which is already in .gitignore. See storage.py for reading
# the value at request time and for generating config/.env.example.

import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Env var names must look like shell variables, so they are safe to
# write into a .env file and read back without surprises.
_ENV_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]*")


class AuthType(str, Enum):
    NONE = "none"
    BEARER = "bearer"
    API_KEY = "api_key"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


def _validate_env_name(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return value

    value = value.strip()

    if not _ENV_NAME_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} must be an environment variable name in "
            f"UPPER_SNAKE_CASE, e.g. STAGING_API_TOKEN (got {value!r})"
        )

    return value


class AuthConfig(BaseModel):
    """
    How to authenticate requests. Only ever stores env var NAMES,
    never the token/key value itself.
    """

    type: AuthType = AuthType.NONE
    token_env: Optional[str] = None            # used when type == bearer
    api_key_header: str = "X-API-Key"
    api_key_env: Optional[str] = None          # used when type == api_key

    @field_validator("token_env", "api_key_env")
    @classmethod
    def _check_env_name(cls, value, info):
        return _validate_env_name(value, info.field_name)

    @model_validator(mode="after")
    def _check_required_env(self):
        if self.type == AuthType.BEARER and not self.token_env:
            raise ValueError("auth type 'bearer' needs token_env (the env var holding the token)")

        if self.type == AuthType.API_KEY and not self.api_key_env:
            raise ValueError("auth type 'api_key' needs api_key_env (the env var holding the key)")

        return self

    def env_names(self) -> List[str]:
        """Every environment variable name this auth config references."""
        return [name for name in (self.token_env, self.api_key_env) if name]


class EndpointConfig(BaseModel):
    name: str
    method: HttpMethod = HttpMethod.GET
    path: str
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Optional[Dict[str, Any]] = None
    timeout: Optional[float] = None            # overrides the API's default
    auth: Optional[AuthConfig] = None          # overrides the API's default auth

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("endpoint name cannot be empty")
        return value

    @field_validator("path")
    @classmethod
    def _path_format(cls, value):
        value = value.strip()
        if not value.startswith("/"):
            raise ValueError("path must start with / (for example /api/v1/health)")
        return value

    @field_validator("timeout")
    @classmethod
    def _timeout_positive(cls, value):
        if value is not None and value <= 0:
            raise ValueError("timeout must be greater than 0")
        return value

    def env_names(self) -> List[str]:
        return self.auth.env_names() if self.auth else []


class APIConfig(BaseModel):
    name: str
    base_url: str
    timeout: float = 10.0
    auth: AuthConfig = Field(default_factory=AuthConfig)
    endpoints: List[EndpointConfig] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name_format(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("API name cannot be empty")
        return value

    @field_validator("base_url")
    @classmethod
    def _base_url_format(cls, value):
        value = value.strip()
        if not re.match(r"^https?://", value):
            raise ValueError("base_url must start with http:// or https://")
        return value.rstrip("/")

    @field_validator("timeout")
    @classmethod
    def _timeout_positive(cls, value):
        if value <= 0:
            raise ValueError("timeout must be greater than 0")
        return value

    @model_validator(mode="after")
    def _unique_endpoint_names(self):
        names = [e.name for e in self.endpoints]

        if len(names) != len(set(names)):
            dupes = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"duplicate endpoint names: {', '.join(dupes)}")

        return self

    def env_names(self) -> List[str]:
        names = list(self.auth.env_names())

        for endpoint in self.endpoints:
            names.extend(endpoint.env_names())

        # de-duplicate, keep a stable order
        seen = []
        for name in names:
            if name not in seen:
                seen.append(name)

        return seen

    def endpoint(self, name: str) -> Optional[EndpointConfig]:
        return next((e for e in self.endpoints if e.name == name), None)

    def effective_auth(self, endpoint: EndpointConfig) -> AuthConfig:
        """The auth that actually applies to this endpoint."""
        return endpoint.auth if endpoint.auth is not None else self.auth

    def effective_timeout(self, endpoint: EndpointConfig) -> float:
        return endpoint.timeout if endpoint.timeout is not None else self.timeout