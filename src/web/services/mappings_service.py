"""Mappings service for CRUD operations and provenance updates."""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import delete

from src.config.database import db
from src.config.settings import get_config
from src.core.mappings import MappingsClient
from src.exceptions import (
    MissingAnilistIdError,
    UnsupportedMappingFileExtensionError,
)
from src.models.db.animap import AniMap
from src.models.db.provenance import AniMapProvenance

__all__ = ["MappingsService", "get_mappings_service"]


@dataclass
class _ActiveFile:
    path: Path
    ext: str


class MappingsService:
    """Service to manage custom mappings and DB provenance."""

    def __init__(self) -> None:
        """Initialize service with config and paths."""
        _config = get_config()
        self.data_path: Path = _config.data_path
        self.upstream_url: str | None = _config.mappings_url

    def _active_custom_file(self) -> _ActiveFile:
        """Determine the active custom mappings file (json/yaml/yml)."""
        for fname in MappingsClient.MAPPING_FILES:
            p = (self.data_path / fname).resolve()
            if p.exists():
                return _ActiveFile(path=p, ext=p.suffix.lstrip("."))
        p = (self.data_path / "mappings.custom.yaml").resolve()
        return _ActiveFile(path=p, ext="yaml")

    def _load_custom(self) -> tuple[_ActiveFile, dict[str, Any]]:
        """Load and parse the active custom mappings file."""
        af = self._active_custom_file()
        if not af.path.exists():
            return af, {}

        try:
            if af.ext == "json":
                return af, json.loads(af.path.read_text(encoding="utf-8"))
            elif af.ext in ("yaml", "yml"):
                return af, yaml.safe_load(af.path.read_text(encoding="utf-8")) or {}
            raise UnsupportedMappingFileExtensionError(
                f"Unsupported file extension: {af.ext}"
            )
        except Exception:
            return af, {}

    def _dump_custom(self, af: _ActiveFile, content: dict[str, Any]) -> None:
        """Dump content to the active custom mappings file."""
        af.path.parent.mkdir(parents=True, exist_ok=True)
        if af.ext == "json":
            af.path.write_text(
                json.dumps(content, indent=2, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
        elif af.ext in ("yaml", "yml"):
            af.path.write_text(
                yaml.safe_dump(content, sort_keys=True, allow_unicode=True),
                encoding="utf-8",
            )
        else:
            raise UnsupportedMappingFileExtensionError(
                f"Unsupported file extension: {af.ext}"
            )

    def _set_provenance_custom_last(self, anilist_id: int, custom_src: str) -> None:
        """Replace provenance entries so that custom is the last source.

        Order becomes [upstream_url? (n=0)], custom (n=last)
        """
        with db() as ctx:
            if ctx.session.get(AniMap, anilist_id) is None:
                return

            ctx.session.execute(
                delete(AniMapProvenance).where(
                    AniMapProvenance.anilist_id == anilist_id
                )
            )

            n = 0
            rows: list[AniMapProvenance] = []
            if self.upstream_url:
                rows.append(
                    AniMapProvenance(
                        anilist_id=anilist_id, n=n, source=self.upstream_url
                    )
                )
                n += 1

            rows.append(
                AniMapProvenance(anilist_id=anilist_id, n=n, source=str(custom_src))
            )
            ctx.session.add_all(rows)
            ctx.session.commit()

    def replace_mapping(self, mapping: dict[str, Any]) -> AniMap:
        """Replace DB row with provided mapping and persist full mapping in custom file.

        Args:
            mapping (dict[str, Any]): Full mapping dict including anilist_id.

        Returns:
            AniMap: The up-to-date DB model.
        """
        if "anilist_id" not in mapping:
            raise MissingAnilistIdError("anilist_id is required")
        anilist_id = int(mapping["anilist_id"])

        defaults = {c.name: None for c in AniMap.__table__.columns}
        payload: dict[str, Any] = {**defaults, **mapping, "anilist_id": anilist_id}

        # List normalization
        for field in ("imdb_id", "mal_id", "tmdb_movie_id", "tmdb_show_id"):
            if field in payload:
                v = payload[field]
                if v is None:
                    payload[field] = None
                elif not isinstance(v, list):
                    payload[field] = [v]

        with db() as ctx:
            ctx.session.execute(delete(AniMap).where(AniMap.anilist_id == anilist_id))
            obj = AniMap(**payload)
            ctx.session.add(obj)
            ctx.session.commit()

        af, content = self._load_custom()
        # Preserve $includes if present
        entry = {k: payload[k] for k in payload if k != "anilist_id"}
        content[str(anilist_id)] = entry
        self._dump_custom(af, content)

        self._set_provenance_custom_last(anilist_id, str(af.path))

        return obj

    def upsert_mapping(self, anilist_id: int, partial: dict[str, Any]) -> AniMap:
        """Upsert DB row applying only provided fields and save partial overlay.

        Args:
            anilist_id (int): The AniList ID of the entry to upsert.
            partial (dict[str, Any]): Partial mapping dict with fields to update.

        Returns:
            AniMap: The up-to-date DB model.
        """
        with db() as ctx:
            obj = ctx.session.get(AniMap, anilist_id)
            if not obj:
                defaults = {c.name: None for c in AniMap.__table__.columns}
                obj = AniMap(**{**defaults, "anilist_id": anilist_id})
                ctx.session.add(obj)

            for k, v in partial.items():
                if k == "anilist_id":
                    continue
                if k not in AniMap.__table__.columns:
                    continue
                if k in ("imdb_id", "mal_id", "tmdb_movie_id", "tmdb_show_id"):
                    if v is None:
                        setattr(obj, k, None)
                    elif isinstance(v, list):
                        setattr(obj, k, v)
                    else:
                        setattr(obj, k, [v])
                else:
                    setattr(obj, k, v)

            ctx.session.commit()

        # Persist partial overlay in custom file
        af, content = self._load_custom()
        existing = content.get(str(anilist_id))
        entry: dict[str, Any] = existing if isinstance(existing, dict) else {}
        for k, v in partial.items():
            if k == "anilist_id":
                continue
            if k not in AniMap.__table__.columns:
                continue
            entry[k] = v

        content[str(anilist_id)] = entry
        self._dump_custom(af, content)

        self._set_provenance_custom_last(anilist_id, str(af.path))

        return obj

    def delete_mapping(self, anilist_id: int) -> None:
        """Delete mapping from DB and shadow upstream by setting null in custom file.

        Args:
            anilist_id (int): The AniList ID of the entry to delete.
        """
        with db() as ctx:
            ctx.session.execute(
                delete(AniMapProvenance).where(
                    AniMapProvenance.anilist_id == anilist_id
                )
            )
            ctx.session.execute(delete(AniMap).where(AniMap.anilist_id == anilist_id))
            ctx.session.commit()

        af, content = self._load_custom()
        content[str(anilist_id)] = None
        self._dump_custom(af, content)


@lru_cache(maxsize=1)
def get_mappings_service() -> MappingsService:
    """Get the singleton instance of the mappings service."""
    return MappingsService()
