"""Service helpers for managing custom mapping overrides."""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, Literal

import yaml
from sqlalchemy.sql import delete

from src import config
from src.config.database import db
from src.core.mappings import MappingsClient
from src.exceptions import (
    MappingError,
    MappingNotFoundError,
    MissingAnilistIdError,
    SchedulerNotInitializedError,
)
from src.models.db.provenance import AniMapProvenance
from src.web.services.mappings_service import get_mappings_service
from src.web.state import get_app_state

__all__ = ["MappingOverridesService", "get_mapping_overrides_service"]


@dataclass(frozen=True)
class _FieldSpec:
    """Specification describing how to sanitize override field values."""

    kind: Literal["scalar", "list", "dict"]
    value_type: type

    def coerce(self, raw_value: Any) -> Any:
        """Coerce a raw value into the expected representation."""
        if raw_value is None:
            return None

        if self.kind == "scalar":
            return self._coerce_scalar(raw_value)
        if self.kind == "list":
            return self._coerce_list(raw_value)
        if self.kind == "dict":
            return self._coerce_dict(raw_value)
        raise ValueError("Unsupported field kind")

    def _coerce_scalar(self, raw_value: Any) -> Any:
        """Coerce a raw scalar value."""
        if self.value_type is int:
            try:
                return int(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError("Expected an integer value") from exc
        if self.value_type is str:
            return str(raw_value)
        return raw_value

    def _coerce_list(self, raw_value: Any) -> list[Any] | None:
        """Coerce a raw list value."""
        if raw_value is None:
            return None
        if isinstance(raw_value, list):
            return [self._coerce_list_item(item) for item in raw_value]
        return [self._coerce_list_item(raw_value)]

    def _coerce_list_item(self, raw_value: Any) -> Any:
        """Coerce a raw list item value."""
        if self.value_type is int:
            try:
                return int(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError("List items must be integers") from exc
        if self.value_type is str:
            return str(raw_value)
        return raw_value

    def _coerce_dict(self, raw_value: Any) -> dict[str, Any] | None:
        """Coerce a raw dict value."""
        if raw_value is None:
            return None
        if not isinstance(raw_value, dict):
            raise ValueError("Expected an object for mapping fields")
        return {
            str(key): str(value) if value is not None else ""
            for key, value in raw_value.items()
        }


class MappingOverridesService:
    """Manage CRUD operations for custom AniMap overrides."""

    _FIELD_SPECS: ClassVar[dict[str, _FieldSpec]] = {
        "anidb_id": _FieldSpec("scalar", int),
        "imdb_id": _FieldSpec("list", str),
        "mal_id": _FieldSpec("list", int),
        "tmdb_movie_id": _FieldSpec("list", int),
        "tmdb_show_id": _FieldSpec("scalar", int),
        "tvdb_id": _FieldSpec("scalar", int),
        "tmdb_mappings": _FieldSpec("dict", str),
        "tvdb_mappings": _FieldSpec("dict", str),
    }

    def __init__(self) -> None:
        """Initialise service state."""
        self._lock = asyncio.Lock()

    def _ensure_scheduler(self):
        """Ensure the application scheduler is available."""
        scheduler = get_app_state().scheduler
        if not scheduler:
            raise SchedulerNotInitializedError("Scheduler not initialised")
        return scheduler

    def _resolve_custom_file(self) -> tuple[Path, Literal["json", "yaml"]]:
        """Determine the custom mappings file path and format."""
        candidates = [config.data_path / name for name in MappingsClient.MAPPING_FILES]
        if not candidates or not candidates[0].exists():
            return config.data_path / "mappings.custom.json", "json"
        if candidates[0].suffix.lower() == ".json":
            return candidates[0], "json"
        return candidates[0], "yaml"

    def _load_raw(self) -> tuple[dict[str, Any], Path, Literal["json", "yaml"]]:
        """Load the raw custom mappings file."""
        path, fmt = self._resolve_custom_file()
        if not path.exists():
            raw: dict[str, Any] = {}
            return raw, path, fmt

        try:
            if fmt == "json":
                with path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            else:
                with path.open("r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
        except Exception as exc:
            raise MappingError("Failed to read custom mappings file") from exc

        if not data:
            data = {}
        if not isinstance(data, dict):
            raise MappingError("Custom mappings file must contain an object")

        return data, path, fmt

    def _write_raw(
        self,
        raw: dict[str, Any],
        path: Path,
        fmt: Literal["json", "yaml"],
    ) -> None:
        """Write the raw custom mappings file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "json":
            with path.open("w", encoding="utf-8") as fh:
                json.dump(raw, fh, indent=2, sort_keys=True)
                fh.write("\n")
        else:
            with path.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(raw, fh, sort_keys=False, allow_unicode=False)

    def _sanitize_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Sanitize a raw override entry."""
        sanitized: dict[str, Any] = {}
        for key, value in entry.items():
            key_str = str(key)
            if key_str.startswith("$"):
                continue
            spec = self._FIELD_SPECS.get(key_str)
            if not spec:
                raise ValueError(f"Unsupported override field '{key_str}'")
            sanitized[key_str] = spec.coerce(value)
        return sanitized

    def _entry_from_fields(
        self, fields: dict[str, dict[str, Any]] | None
    ) -> dict[str, Any]:
        """Construct an override entry from field-based specifications."""
        if not fields:
            return {}
        entry: dict[str, Any] = {}
        for raw_name, payload in fields.items():
            name = str(raw_name)
            spec = self._FIELD_SPECS.get(name)
            if not spec:
                raise ValueError(f"Unsupported override field '{name}'")

            mode = str(payload.get("mode", "omit")).lower()
            if mode == "omit":
                continue
            if mode == "null":
                entry[name] = None
                continue
            if mode != "value":
                raise ValueError(f"Invalid mode '{mode}' for field '{name}'")

            if "value" not in payload:
                raise ValueError(f"Field '{name}' requires a value")
            entry[name] = spec.coerce(payload.get("value"))
        return entry

    async def _sync_database(self) -> None:
        scheduler = self._ensure_scheduler()
        await scheduler.shared_animap_client.sync_db()

    async def get_mapping_detail(self, anilist_id: int) -> dict[str, Any]:
        """Return mapping and override information for a single AniList ID.

        Args:
            anilist_id (int): The AniList ID of the mapping to retrieve.

        Returns:
            dict[str, Any]: The mapping detail, including any override data.
        """
        async with self._lock:
            raw, _, _ = self._load_raw()
            override = copy.deepcopy(raw.get(str(anilist_id)))

        try:
            item = await get_mappings_service().get_mapping(
                anilist_id, with_anilist=True
            )
        except MappingNotFoundError:
            item = {
                "anilist_id": anilist_id,
                "custom": bool(override),
                "sources": ["custom"] if override else [],
            }

        item.setdefault("override", override)
        if override is None:
            item["override"] = None
        return item

    async def save_override(
        self,
        *,
        anilist_id: int | None,
        fields: dict[str, dict[str, Any]] | None,
        raw: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Persist override changes and refresh the AniMap database.

        Args:
            anilist_id (int | None): The AniList ID of the mapping to modify.
            fields (dict[str, dict[str, Any]] | None): Field-based override
                specifications.
            raw (dict[str, Any] | None): Raw override entry.

        Returns:
            dict[str, Any]: The updated mapping detail.
        """
        if anilist_id is None:
            raise MissingAnilistIdError("anilist_id is required")

        async with self._lock:
            raw_file, path, fmt = self._load_raw()
            key = str(anilist_id)

            if raw is not None:
                if not isinstance(raw, dict):
                    raise ValueError("Override payload must be an object")
                entry = self._sanitize_entry(raw)
            else:
                entry = self._entry_from_fields(fields)

            if entry:
                raw_file[key] = entry
            else:
                raw_file.pop(key, None)

            self._write_raw(raw_file, path, fmt)

        await self._sync_database()
        return await self.get_mapping_detail(anilist_id)

    async def delete_override(
        self,
        anilist_id: int,
        *,
        mode: Literal["custom", "full"] = "custom",
    ) -> None:
        """Remove an override or replace it with a null override marker.

        Args:
            anilist_id (int): The AniList ID of the mapping to modify.
            mode (Literal["custom", "full"]): The deletion mode. If "custom",
                the override entry is removed entirely. If "full", the override
                entry is replaced with a null value to omit the mapping from AniMap.

        Raises:
            MappingNotFoundError: If the mapping does not exist.
        """
        async with self._lock:
            raw, path, fmt = self._load_raw()
            key = str(anilist_id)

            if mode == "custom":
                raw.pop(key, None)
            else:
                raw[key] = None

            self._write_raw(raw, path, fmt)

        with db() as ctx:
            source = str(self._resolve_custom_file()[0].resolve())
            print(source)
            delete_stmt = delete(AniMapProvenance).where(
                AniMapProvenance.anilist_id == anilist_id,
                AniMapProvenance.source == source,
            )
            ctx.session.execute(delete_stmt)
            ctx.session.commit()

        await self._sync_database()


@lru_cache(maxsize=1)
def get_mapping_overrides_service() -> MappingOverridesService:
    """Return the singleton mapping override service.

    Returns:
        MappingOverridesService: The mapping overrides service instance.
    """
    return MappingOverridesService()
