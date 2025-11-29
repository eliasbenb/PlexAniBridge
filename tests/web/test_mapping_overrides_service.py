"""Tests for the mapping overrides service."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from src import config as app_config
from src.config.database import db
from src.models.db.animap import AniMap
from src.models.db.provenance import AniMapProvenance
from src.web.services import mappings_service as mappings_service_module
from src.web.services.mapping_overrides_service import MappingOverridesService
from src.web.state import get_app_state


class DummyScheduler:
    """Scheduler double exposing only the sync_db hook."""

    def __init__(self) -> None:
        """Initialise tracking flags and shared AniMap client stub."""
        self.synced = False
        self.shared_animap_client = SimpleNamespace(sync_db=self._sync_db)

    async def _sync_db(self) -> None:
        self.synced = True


@pytest.fixture()
def overrides_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate mapping override files under a temporary data directory."""
    monkeypatch.setattr(app_config, "data_path", tmp_path)
    scheduler = DummyScheduler()
    state = get_app_state()
    state.scheduler = cast(Any, scheduler)

    async def fake_get_mapping(anilist_id: int, **_kwargs):
        return {"anilist_id": anilist_id, "custom": True, "sources": ["custom"]}

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
async def test_save_override_writes_file_and_syncs_db(overrides_env):
    """save_override persists sanitized payloads and triggers DB sync."""
    tmp_path, scheduler = overrides_env
    service = MappingOverridesService()

    result = await service.save_override(
        anilist_id=101,
        fields=None,
        raw={"mal_id": ["1", "2"], "tmdb_show_id": "8"},
    )
    assert result["override"] == {"mal_id": [1, 2], "tmdb_show_id": 8}

    data = json.loads((tmp_path / "mappings.custom.json").read_text(encoding="utf-8"))
    assert data[str(101)] == {"mal_id": [1, 2], "tmdb_show_id": 8}
    assert scheduler.synced is True


@pytest.mark.asyncio
async def test_save_override_supports_field_specs(overrides_env):
    """Field-based payloads respect mode handling and validation."""
    tmp_path, _ = overrides_env
    service = MappingOverridesService()

    payload = {
        "mal_id": {"mode": "value", "value": ["3", "4"]},
        "tmdb_movie_id": {"mode": "omit"},
        "tmdb_show_id": {"mode": "null"},
    }
    await service.save_override(anilist_id=202, fields=payload, raw=None)

    data = json.loads((tmp_path / "mappings.custom.json").read_text(encoding="utf-8"))
    assert data[str(202)] == {"mal_id": [3, 4], "tmdb_show_id": None}


@pytest.mark.asyncio
async def test_delete_override_modes(overrides_env):
    """delete_override removes entries or writes null markers based on mode."""
    tmp_path, _ = overrides_env
    service = MappingOverridesService()

    await service.save_override(anilist_id=303, fields=None, raw={"mal_id": [1]})
    file_path = tmp_path / "mappings.custom.json"

    # Seed provenance row to exercise deletion query
    with db() as ctx:
        ctx.session.merge(AniMap(anilist_id=303))
        ctx.session.merge(
            AniMapProvenance(
                anilist_id=303,
                n=1,
                source=str(file_path.resolve()),
            )
        )
        ctx.session.commit()

    await service.delete_override(303, mode="custom")
    data = json.loads(file_path.read_text(encoding="utf-8"))
    assert str(303) not in data

    await service.delete_override(404, mode="full")
    data = json.loads(file_path.read_text(encoding="utf-8"))
    assert data[str(404)] is None
