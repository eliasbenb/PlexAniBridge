"""Service helpers for managing custom mapping overrides (v3 graph)."""

import asyncio
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import yaml

from src import config
from src.core.animap import MappingDescriptor
from src.core.mappings import MappingsClient
from src.exceptions import (
    MappingError,
    MappingNotFoundError,
    MissingDescriptorError,
    SchedulerNotInitializedError,
)
from src.web.services.mappings_service import get_mappings_service
from src.web.state import get_app_state

__all__ = ["MappingOverridesService", "get_mapping_overrides_service"]


@dataclass(frozen=True)
class OverridePayload:
    """Override payload for a single descriptor."""

    descriptor: str
    targets: dict[str, dict[str, str | None]]


@dataclass(frozen=True)
class StructuredEdge:
    """Structured override edge definition."""

    target: str
    source_range: str
    destination_range: str | None


class MappingOverridesService:
    """Manage CRUD operations for custom mapping overrides (descriptor graph)."""

    _SUPPORTED_FORMATS: ClassVar[tuple[str, ...]] = ("json", "yaml")

    def __init__(self) -> None:
        """Initialise synchronization primitives for override operations."""
        self._lock = asyncio.Lock()

    def _ensure_scheduler(self):
        """Ensure the scheduler is available and return it."""
        scheduler = get_app_state().scheduler
        if not scheduler:
            raise SchedulerNotInitializedError("Scheduler not initialized")
        return scheduler

    def _resolve_custom_file(self) -> tuple[Path, str]:
        """Determine the path and format of the custom mappings override file."""
        candidates = [config.data_path / name for name in MappingsClient.MAPPING_FILES]
        if not candidates or not candidates[0].exists():
            return config.data_path / "mappings.json", "json"
        if candidates[0].suffix.lower() == ".json":
            return candidates[0], "json"
        return candidates[0], "yaml"

    def _load_raw(self) -> tuple[dict[str, Any], Path, str]:
        """Load raw override data from the custom mappings file."""
        path, fmt = self._resolve_custom_file()
        if not path.exists():
            return {}, path, fmt

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

    def _write_raw(self, raw: dict[str, Any], path: Path, fmt: str) -> None:
        """Persist raw override data to the custom mappings file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "json":
            with path.open("w", encoding="utf-8") as fh:
                json.dump(raw, fh, indent=2, sort_keys=True)
                fh.write("\n")
        else:
            with path.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(raw, fh, sort_keys=False, allow_unicode=False)

    def _merge_structured_edges(
        self, targets: dict[str, dict[str, str | None]], edges: list[StructuredEdge]
    ) -> dict[str, dict[str, str | None]]:
        """Merge structured edge payloads into the target mapping shape."""
        merged = {dst: dict(ranges) for dst, ranges in targets.items()}
        for edge in edges:
            bucket = merged.setdefault(edge.target, {})
            bucket[edge.source_range] = edge.destination_range
        return merged

    def _validate_structured_edges(
        self, edges: list[dict[str, Any]] | None
    ) -> list[StructuredEdge]:
        """Validate structured edge inputs and normalize into dataclasses."""
        if not edges:
            return []
        normalized: list[StructuredEdge] = []
        for raw in edges:
            target = str(raw.get("target")) if raw.get("target") is not None else ""
            src_range = raw.get("source_range")
            dst_range = raw.get("destination_range")
            if not target:
                raise MappingError("edge.target is required")
            if not isinstance(src_range, str) or not src_range:
                raise MappingError("edge.source_range must be a non-empty string")
            if dst_range is not None and not isinstance(dst_range, str):
                raise MappingError("edge.destination_range must be a string or null")
            MappingDescriptor.parse(target)
            normalized.append(
                StructuredEdge(
                    target=target,
                    source_range=src_range,
                    destination_range=dst_range,
                )
            )
        return normalized

    def _validate_payload(
        self,
        descriptor: str,
        targets: dict[str, Any] | None,
        edges: list[dict[str, Any]] | None,
    ) -> OverridePayload:
        """Validate and parse an override payload."""
        if not descriptor:
            raise MissingDescriptorError("descriptor is required")
        MappingDescriptor.parse(descriptor)

        parsed_targets: dict[str, dict[str, str | None]] = {}
        for raw_dst, ranges in (targets or {}).items():
            MappingDescriptor.parse(raw_dst)
            if not isinstance(ranges, dict):
                raise MappingError(
                    "targets must be a mapping of destination descriptors to range maps"
                )
            cleaned: dict[str, str | None] = {}
            for src_range, dst_range in ranges.items():
                if not isinstance(src_range, str) or not src_range:
                    raise MappingError("source ranges must be non-empty strings")
                if dst_range is not None and not isinstance(dst_range, str):
                    raise MappingError("destination ranges must be strings or null")
                cleaned[src_range] = dst_range
            parsed_targets[raw_dst] = cleaned

        structured_edges = self._validate_structured_edges(edges)
        if structured_edges:
            parsed_targets = self._merge_structured_edges(
                parsed_targets, structured_edges
            )

        return OverridePayload(descriptor=descriptor, targets=parsed_targets)

    async def _sync_database(self) -> None:
        """Trigger a synchronization of the AniMap database."""
        scheduler = self._ensure_scheduler()
        await scheduler.shared_animap_client.sync_db()

    @staticmethod
    def _override_edges_from_targets(
        targets: dict[str, dict[str, str | None]] | None,
    ) -> list[dict[str, str | None]]:
        """Convert the stored targets mapping into a structured edge list."""
        if not targets:
            return []
        edges: list[dict[str, str | None]] = []
        for target, ranges in targets.items():
            for source_range, destination_range in (ranges or {}).items():
                edges.append(
                    {
                        "target": target,
                        "source_range": source_range,
                        "destination_range": destination_range,
                    }
                )
        return edges

    async def get_mapping_detail(self, descriptor: str) -> dict[str, Any]:
        """Fetch mapping detail merged with any override for the descriptor.

        Args:
            descriptor (str): The mapping descriptor to fetch.

        Returns:
            dict[str, Any]: The mapping detail with any override applied.
        """
        async with self._lock:
            raw, _, _ = self._load_raw()
            override = copy.deepcopy(raw.get(descriptor))

        try:
            item = await get_mappings_service().get_mapping(descriptor)
        except MappingNotFoundError:
            parsed = MappingDescriptor.parse(descriptor)
            item = {
                "descriptor": descriptor,
                "provider": parsed.provider,
                "entry_id": parsed.entry_id,
                "scope": parsed.scope,
                "edges": [],
                "custom": bool(override),
                "sources": ["custom"] if override else [],
            }

        item.setdefault("override", override)
        item["override_edges"] = self._override_edges_from_targets(override)
        return item

    async def save_override(
        self,
        *,
        descriptor: str | None,
        targets: dict[str, Any] | None,
        edges: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Persist an override for a descriptor and trigger DB sync.

        Args:
            descriptor (str | None): The mapping descriptor to override.
            targets (dict[str, Any] | None): The target mappings.
            edges (list[dict[str, Any]] | None): Structured edge definitions.

        Returns:
            dict[str, Any]: The updated mapping detail with override applied.
        """
        if descriptor is None:
            raise MissingDescriptorError("descriptor is required")
        payload = self._validate_payload(descriptor, targets, edges)

        async with self._lock:
            raw, path, fmt = self._load_raw()
            raw[payload.descriptor] = payload.targets
            self._write_raw(raw, path, fmt)

        await self._sync_database()
        return await self.get_mapping_detail(payload.descriptor)

    async def delete_override(self, descriptor: str) -> dict[str, Any]:
        """Remove an override for the given descriptor and sync the DB.

        Args:
            descriptor (str): The mapping descriptor to remove the override for.

        Returns:
            dict[str, Any]: Confirmation of successful deletion.
        """
        payload = MappingDescriptor.parse(descriptor)
        async with self._lock:
            raw, path, fmt = self._load_raw()
            raw.pop(payload.key(), None)
            self._write_raw(raw, path, fmt)

        await self._sync_database()
        return {"ok": True}


_mapping_overrides_service: MappingOverridesService | None = None


def get_mapping_overrides_service() -> MappingOverridesService:
    """Return a singleton mapping overrides service instance.

    Returns:
        MappingOverridesService: The singleton service instance.
    """
    global _mapping_overrides_service
    if _mapping_overrides_service is None:
        _mapping_overrides_service = MappingOverridesService()
    return _mapping_overrides_service
