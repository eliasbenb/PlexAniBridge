"""Unit tests for the pin management service."""

from datetime import UTC, datetime, timedelta

import pytest

from src.config.database import db
from src.config.settings import SyncField
from src.models.db.pin import Pin
from src.web.services.pin_service import PinService, UpdatePinPayload


@pytest.fixture(autouse=True)
def _clear_pins():
    """Ensure the pin table is empty before and after each test."""
    with db() as ctx:
        ctx.session.query(Pin).delete()
        ctx.session.commit()
    yield
    with db() as ctx:
        ctx.session.query(Pin).delete()
        ctx.session.commit()


def _insert_pin(**overrides) -> Pin:
    now = datetime.now(UTC) - timedelta(days=1)
    pin = Pin(
        profile_name=overrides.get("profile_name", "default"),
        list_namespace=overrides.get("list_namespace", "anilist"),
        list_media_key=overrides.get("list_media_key", "abc"),
        fields=overrides.get("fields", [SyncField.STATUS.value]),
        created_at=overrides.get("created_at", now),
        updated_at=overrides.get("updated_at", now),
    )
    with db() as ctx:
        ctx.session.add(pin)
        ctx.session.commit()
        ctx.session.refresh(pin)
    return pin


def test_update_pin_payload_normalizes_and_validates():
    """Normalize payloads into SyncField order and reject invalid fields."""
    payload = UpdatePinPayload(
        fields=[
            SyncField.STATUS,
            " progress ",
            SyncField.STATUS,  # duplicate
            "USER_RATING",
        ]
    )
    assert payload.normalized() == [
        SyncField.STATUS.value,
        SyncField.PROGRESS.value,
        SyncField.USER_RATING.value,
    ]

    with pytest.raises(ValueError, match="Unsupported field"):
        UpdatePinPayload(fields=["missing"]).normalized()


def test_pin_service_lists_and_serializes_entries():
    """Return entries ordered by most recent update and serialize fields."""
    service = PinService()
    _insert_pin(list_media_key="1", fields=[SyncField.STATUS.value])
    newer = _insert_pin(
        list_media_key="2",
        fields=[SyncField.USER_RATING.value],
        updated_at=datetime.now(UTC),
    )

    pins = service.list_pins("default")
    assert [pin.list_media_key for pin in pins] == ["2", "1"]
    assert pins[0].fields == [SyncField.USER_RATING.value]

    fetched = service.get_pin("default", newer.list_namespace, newer.list_media_key)
    assert fetched is not None
    assert fetched.fields == newer.fields


def test_pin_service_upsert_and_delete_roundtrip():
    """Upsert pins, refresh timestamps, and delete entries cleanly."""
    service = PinService()

    created = service.upsert_pin(
        "default",
        "anilist",
        "abc",
        [SyncField.PROGRESS.value, SyncField.STATUS.value],
    )
    assert sorted(created.fields) == [SyncField.PROGRESS.value, SyncField.STATUS.value]

    updated = service.upsert_pin(
        "default",
        "anilist",
        "abc",
        [SyncField.REPEATS.value],
    )
    assert updated.fields == [SyncField.REPEATS.value]
    assert updated.updated_at >= created.updated_at

    service.delete_pin("default", "anilist", "abc")
    assert service.get_pin("default", "anilist", "abc") is None

    with pytest.raises(ValueError):
        service.upsert_pin("default", "anilist", "xyz", [])
