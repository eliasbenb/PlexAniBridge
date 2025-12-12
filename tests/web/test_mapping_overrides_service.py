"""Tests for the mapping overrides service (v3)."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from src import config as app_config
from src.config.database import db
from src.core.animap import MappingDescriptor
from src.models.db.animap import AnimapEntry, AnimapMapping, AnimapProvenance
from src.web.services import mappings_service as mappings_service_module
from src.web.services.mapping_overrides_service import MappingOverridesService
from src.web.state import get_app_state


class DummyScheduler:
    """Scheduler double exposing only the sync_db hook."""

    def __init__(self) -> None:
        """Initialize the dummy scheduler."""
        self.synced = False
        self.shared_animap_client = SimpleNamespace(sync_db=self._sync_db)

    async def _sync_db(self) -> None:
        self.synced = True


@pytest.fixture()
def overrides_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up environment for mapping overrides tests."""
    monkeypatch.setattr(app_config, "data_path", tmp_path)
    scheduler = DummyScheduler()
    state = get_app_state()
    state.scheduler = cast(Any, scheduler)

    async def fake_get_mapping(descriptor: str, **_kwargs):
        parsed = MappingDescriptor.parse(descriptor)
        return {
            "descriptor": descriptor,
            "provider": parsed.provider,
            "entry_id": parsed.entry_id,
            "scope": parsed.scope,
            "edges": [],
            "custom": True,
            "sources": ["custom"],
        }

    monkeypatch.setattr(
        mappings_service_module,
        "get_mappings_service",
        lambda: SimpleNamespace(get_mapping=fake_get_mapping),
    )
    monkeypatch.setattr(
        mappings_service_module.MappingsService,
        "_FIELD_MAP",
        mappings_service_module.get_query_field_map(),
        raising=False,
    )
    yield tmp_path, scheduler
    state.scheduler = None


@pytest.mark.asyncio
async def test_save_override_writes_file_and_syncs_db(
    overrides_env: tuple[Path, DummyScheduler],
) -> None:
    """Saving an override persists to file and triggers DB sync."""
    tmp_path, scheduler = overrides_env
    service = MappingOverridesService()

    result = await service.save_override(
        descriptor="anilist:101:movie",
        targets={"tmdb:202:movie": {"1": None}},
    )
    assert result["descriptor"] == "anilist:101:movie"

    data = json.loads((tmp_path / "mappings.json").read_text(encoding="utf-8"))
    assert data["anilist:101:movie"] == {"tmdb:202:movie": {"1": None}}
    assert scheduler.synced is True


@pytest.mark.asyncio
async def test_delete_override_removes_entry(
    overrides_env: tuple[Path, DummyScheduler],
) -> None:
    """Deleting an override removes it from the file and syncs the DB."""
    tmp_path, _ = overrides_env
    service = MappingOverridesService()

    await service.save_override(
        descriptor="anilist:303:movie",
        targets={"tmdb:404:movie": {"1": None}},
    )
    file_path = tmp_path / "mappings.json"
    with db() as ctx:
        src = AnimapEntry(provider="anilist", entry_id="303", entry_scope="movie")
        dst = AnimapEntry(provider="tmdb", entry_id="404", entry_scope="movie")
        ctx.session.add_all([src, dst])
        ctx.session.flush()
        mapping = AnimapMapping(
            source_entry_id=src.id,
            destination_entry_id=dst.id,
            source_range="1",
            destination_range=None,
        )
        ctx.session.add(mapping)
        ctx.session.flush()
        ctx.session.add(
            AnimapProvenance(
                mapping_id=mapping.id,
                n=1,
                source=str(file_path.resolve()),
            )
        )
        ctx.session.commit()

    await service.delete_override("anilist:303:movie")
    data = json.loads(file_path.read_text(encoding="utf-8"))
    assert "anilist:303:movie" not in data
