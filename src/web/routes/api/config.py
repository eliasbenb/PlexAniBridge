"""Configuration management API endpoints."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, ValidationError

from src.config.settings import AniBridgeConfig
from src.web.services.configuration_service import ConfigurationService

__all__ = ["router"]


class ConfigDocumentResponse(BaseModel):
    config_path: str
    file_exists: bool
    content: str
    mtime: int | None = None


class ConfigDocumentUpdateRequest(BaseModel):
    content: str = Field(min_length=0)
    expected_mtime: int | None = None


class ConfigUpdateResponse(BaseModel):
    ok: bool
    profiles: list[str]
    requires_restart: bool = True
    mtime: int | None = None


router = APIRouter()

_config_service = ConfigurationService()


@router.get("", response_model=ConfigDocumentResponse)
def get_configuration() -> ConfigDocumentResponse:
    """Return the current configuration as raw YAML text.

    Returns:
        ConfigDocumentResponse: The configuration document details.
    """
    try:
        payload = _config_service.load_document_text()
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ConfigDocumentResponse(**payload)


@router.post("", response_model=ConfigUpdateResponse)
async def update_configuration(
    request: ConfigDocumentUpdateRequest,
) -> ConfigUpdateResponse:
    """Persist the provided configuration document.

    Args:
        request (ConfigDocumentUpdateRequest): The configuration update request.

    Returns:
        ConfigUpdateResponse: The result of the update operation.
    """
    try:
        config, mtime = await _config_service.save_document_text(
            request.content,
            expected_mtime=request.expected_mtime,
        )
    except FileExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ConfigUpdateResponse(
        ok=True,
        profiles=sorted(config.profiles.keys()),
        requires_restart=True,
        mtime=mtime,
    )


@router.get("/openapi.json")
def get_openapi_schema() -> dict:
    """Return the OpenAPI schema for the configuration API.

    Returns:
        dict: OpenAPI schema
    """
    return AniBridgeConfig.model_json_schema()
