"""Service for reading/writing custom override mappings.

This persists only user overrides in mappings.custom.{yaml,yml,json}, using a
dictionary keyed by AniList ID (as string). Values contain only override fields
(do not duplicate the key inside the object).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from src import log
from src.config import config


class MappingsStore:
    """Load, persist, and query custom override mappings file."""

    MAPPINGS_FILENAMES = [
        "mappings.custom.yaml",
        "mappings.custom.yml",
        "mappings.custom.json",
    ]

    def __init__(self, base_dir: Path) -> None:
        """Initialize the MappingsStore."""
        self.base_dir = base_dir
        self.file_path = self._resolve_file()
        # Cache: dict[str(anilist_id)] -> dict(fields overrides)
        self._cache: dict[str, dict[str, Any]] = {}
        self._load()

    def _resolve_file(self) -> Path:
        """Resolve the mappings file path.

        Returns:
            Path: The resolved mappings file path.
        """
        for name in MappingsStore.MAPPINGS_FILENAMES:
            p = self.base_dir / name
            if p.exists():
                return p
        # Default to YAML custom file if none exists
        return self.base_dir / "mappings.custom.yaml"

    def _load(self) -> None:
        """Load the mappings from the file."""
        if not self.file_path.exists():
            self._cache = {}
            return
        try:
            if self.file_path.suffix == ".json":
                data = json.loads(self.file_path.read_text())
            else:
                data = yaml.safe_load(self.file_path.read_text()) or {}
            # Normalize to dict[str, dict]
            if isinstance(data, list):
                conv: dict[str, dict[str, Any]] = {}
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    key = item.get("anilist_id") or item.get("id")
                    if key is None:
                        continue
                    k = str(key)
                    v = {
                        k2: v2
                        for k2, v2 in item.items()
                        if k2 not in {"anilist_id", "id"}
                    }
                    conv[k] = v
                self._cache = conv
            elif isinstance(data, dict):
                self._cache = {
                    str(k): (v or {})
                    for k, v in data.items()
                    if isinstance(v, dict) or v is None
                }
            else:
                self._cache = {}
        except Exception as e:
            log.error(f"MappingsStore: Failed to load mappings: {e}")
            self._cache = {}

    def _persist(self) -> None:
        """Persist the mappings to the file."""
        try:
            if self.file_path.suffix == ".json":
                self.file_path.write_text(
                    json.dumps(self._cache, indent=2, ensure_ascii=False)
                )
            else:
                self.file_path.write_text(
                    yaml.safe_dump(self._cache, sort_keys=False, allow_unicode=True)
                )
        except Exception as e:
            log.error(f"MappingsStore: Failed to write mappings: {e}")

    def list(self, search: str | None, page: int, per_page: int) -> dict[str, Any]:
        """List mappings with optional search and pagination.

        Args:
            search (str | None): The search term to filter mappings.
            page (int): The page number to retrieve.
            per_page (int): The number of items per page.

        Returns:
            dict[str, Any]: The paginated list of mappings.
        """
        items = [{"anilist_id": int(k), **(v or {})} for k, v in self._cache.items()]
        if search:
            s = search.lower()
            items = [m for m in items if s in json.dumps(m).lower()]
        total = len(items)
        start = (page - 1) * per_page
        end = min(start + per_page, total)
        return {
            "items": items[start:end],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    def upsert(
        self, mapping: dict[str, Any], key_field: str = "anilist_id"
    ) -> dict[str, Any]:
        """Upsert an override mapping into the store.

        Args:
            mapping (dict[str, Any]): The mapping to upsert.
            key_field (str): The field to use as the unique key.

        Returns:
            dict[str, Any]: The upserted mapping.
        """
        key = mapping.get(key_field) or mapping.get("id")
        if key is None:
            raise ValueError("'anilist_id' (or 'id') is required for overrides")
        k = str(int(key))
        value = {k2: v2 for k2, v2 in mapping.items() if k2 not in {"anilist_id", "id"}}
        self._cache[k] = value
        self._persist()
        return {"anilist_id": int(k), **value}

    def delete(self, key: int, key_field: str = "anilist_id") -> bool:
        """Delete an override mapping from the store.

        Args:
            key (int): The unique key of the mapping to delete.
            key_field (str): The field to use as the unique key.

        Returns:
            bool: True if the mapping was deleted, False otherwise.
        """
        k = str(int(key))
        if k in self._cache:
            del self._cache[k]
            self._persist()
            return True
        return False

    def get(self, key: int, key_field: str = "anilist_id") -> dict[str, Any] | None:
        """Retrieve a single override by its key.

        Args:
            key (int): The unique key of the mapping to retrieve.
            key_field (str): The field used as the unique key.

        Returns:
            dict[str, Any] | None: The mapping if found, else None.
        """
        k = str(int(key))
        v = self._cache.get(k)
        if v is None:
            return None
        return {"anilist_id": int(k), **v}

    def keys(self) -> list[int]:
        """Return list of AniList IDs that have custom overrides.

        Returns:
            list[int]: The list of AniList IDs present in the custom store.
        """
        return [int(k) for k in self._cache]


_mappings_store: MappingsStore | None = None


def get_mappings_store() -> MappingsStore:
    """Get the global mappings store instance."""
    global _mappings_store
    if _mappings_store is None:
        _mappings_store = MappingsStore(config.data_path)
    return _mappings_store
