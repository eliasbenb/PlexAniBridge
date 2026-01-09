"""Tests for the mapping overrides service (v3)."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from src import config as app_config
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
        targets=[
            {
                "provider": "tmdb",
                "entry_id": "202",
                "scope": "movie",
                "ranges": [
                    {
                        "source_range": "1",
                        "destination_range": None,
                    }
                ],
            }
        ],
    )
    assert result["descriptor"] == "anilist:101:movie"
    assert result["layers"]["effective"]["tmdb:202:movie"]["1"] is None

    data = json.loads((tmp_path / "mappings.json").read_text(encoding="utf-8"))
    assert data["anilist:101:movie"] == {"tmdb:202:movie": {"1": None}}
    assert scheduler.synced is True


@pytest.mark.asyncio
async def test_get_mapping_detail_layers_upstream_and_custom(
    overrides_env: tuple[Path, DummyScheduler], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Detail view includes upstream placeholders and custom overrides."""
    service = MappingOverridesService()

    async def fake_load_upstream(self):
        return {"anilist:909:movie": {"tmdb:777:movie": {"1": "1..3"}}}

    monkeypatch.setattr(MappingOverridesService, "_load_upstream", fake_load_upstream)

    await service.save_override(
        descriptor="anilist:909:movie",
        targets=[
            {
                "provider": "tmdb",
                "entry_id": "777",
                "scope": "movie",
                "ranges": [
                    {
                        "source_range": "1",
                        "destination_range": None,
                    }
                ],
            }
        ],
    )

    detail = await service.get_mapping_detail("anilist:909:movie")
    assert detail["layers"]["upstream"]["tmdb:777:movie"]["1"] == "1..3"
    assert detail["layers"]["custom"]["tmdb:777:movie"]["1"] is None
    assert detail["layers"]["effective"]["tmdb:777:movie"]["1"] is None

    assert detail["targets"]
    entry = detail["targets"][0]
    assert entry["origin"] == "mixed"
    assert entry["ranges"] == [
        {
            "source_range": "1",
            "upstream": "1..3",
            "custom": None,
            "effective": None,
            "origin": "custom",
            "inherited": False,
        }
    ]
