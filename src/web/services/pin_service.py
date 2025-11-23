"""Service for managing provider-specific field pins per profile."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

from pydantic import BaseModel, Field

from src.config.database import db
from src.config.settings import SyncField
from src.models.db.pin import Pin
from src.models.schemas.provider import ProviderMediaMetadata

__all__ = [
    "PinEntry",
    "PinFieldOption",
    "PinService",
    "UpdatePinPayload",
    "get_pin_service",
]


_PIN_LABELS: dict[str, str] = {
    SyncField.STATUS.value: "Status",
    SyncField.SCORE.value: "Score",
    SyncField.PROGRESS.value: "Progress",
    SyncField.REPEAT.value: "Rewatch Count",
    SyncField.NOTES.value: "Notes",
    SyncField.STARTED_AT.value: "Started Date",
    SyncField.COMPLETED_AT.value: "Completed Date",
}


class PinFieldOption(BaseModel):
    """Metadata for a selectable pin field."""

    value: str
    label: str


class PinEntry(BaseModel):
    """Serialized representation of a pin row."""

    profile_name: str
    list_namespace: str
    list_media_key: str
    fields: list[str]
    created_at: datetime
    updated_at: datetime
    media: ProviderMediaMetadata | None = None


class UpdatePinPayload(BaseModel):
    """Payload accepted when updating pin configuration."""

    fields: list[str] = Field(default_factory=list)

    def normalized(self) -> list[str]:
        """Return sanitized field names as SyncField values."""
        allowed = {f.value for f in SyncField}
        values = []
        for field in self.fields:
            if isinstance(field, SyncField):
                value = field.value
            else:
                value = str(field).strip().lower()
            if not value:
                continue
            if value not in allowed:
                raise ValueError(f"Unsupported field '{field}'")
            values.append(value)
        # Preserve order based on SyncField declaration while ensuring uniqueness
        ordered: list[str] = []
        for candidate in SyncField:
            if candidate.value in values and candidate.value not in ordered:
                ordered.append(candidate.value)
        return ordered


@dataclass
class PinService:
    """Service encapsulating pin CRUD operations."""

    allowed_fields: tuple[str, ...] = tuple(field.value for field in SyncField)

    def list_options(self) -> list[PinFieldOption]:
        """Return metadata for selectable fields."""
        return [
            PinFieldOption(value=value, label=_PIN_LABELS.get(value, value.title()))
            for value in self.allowed_fields
        ]

    def list_pins(self, profile: str) -> list[PinEntry]:
        """Return all pins for a profile ordered by most recent."""
        with db() as ctx:
            rows = (
                ctx.session.query(Pin)
                .filter(Pin.profile_name == profile)
                .order_by(Pin.updated_at.desc())
                .all()
            )

        return [self._serialize(row) for row in rows]

    def get_pin(self, profile: str, namespace: str, media_key: str) -> PinEntry | None:
        """Return a single pin entry if it exists."""
        with db() as ctx:
            pin = (
                ctx.session.query(Pin)
                .filter(
                    Pin.profile_name == profile,
                    Pin.list_namespace == namespace,
                    Pin.list_media_key == media_key,
                )
                .first()
            )

        return self._serialize(pin) if pin else None

    def upsert_pin(
        self, profile: str, namespace: str, media_key: str, fields: Iterable[str]
    ) -> PinEntry:
        """Create or update a pin configuration."""
        sanitized = self._sanitize_fields(fields)
        if not sanitized:
            raise ValueError("At least one field must be provided")

        with db() as ctx:
            pin = (
                ctx.session.query(Pin)
                .filter(
                    Pin.profile_name == profile,
                    Pin.list_namespace == namespace,
                    Pin.list_media_key == media_key,
                )
                .first()
            )

            now = datetime.now(UTC)
            if not pin:
                pin = Pin(
                    profile_name=profile,
                    list_namespace=namespace,
                    list_media_key=media_key,
                    fields=sanitized,
                    created_at=now,
                    updated_at=now,
                )
                ctx.session.add(pin)
            else:
                pin.fields = sanitized
                pin.updated_at = now

            ctx.session.commit()
            ctx.session.refresh(pin)

        return self._serialize(pin)

    def delete_pin(self, profile: str, namespace: str, media_key: str) -> None:
        """Remove a pin configuration if it exists."""
        with db() as ctx:
            pin = (
                ctx.session.query(Pin)
                .filter(
                    Pin.profile_name == profile,
                    Pin.list_namespace == namespace,
                    Pin.list_media_key == media_key,
                )
                .first()
            )
            if not pin:
                return
            ctx.session.delete(pin)
            ctx.session.commit()

    def _sanitize_fields(self, fields: Iterable[str]) -> list[str]:
        allowed = set(self.allowed_fields)
        sanitized: list[str] = []
        for field in fields:
            value = str(field).strip().lower()
            if not value:
                continue
            if value not in allowed:
                raise ValueError(f"Unsupported field '{field}'")
            if value not in sanitized:
                sanitized.append(value)
        return sanitized

    @staticmethod
    def _serialize(pin: Pin, media: ProviderMediaMetadata | None = None) -> PinEntry:
        return PinEntry(
            profile_name=pin.profile_name,
            list_namespace=pin.list_namespace,
            list_media_key=pin.list_media_key,
            fields=list(pin.fields or []),
            created_at=pin.created_at,
            updated_at=pin.updated_at,
            media=media,
        )


@lru_cache(maxsize=1)
def get_pin_service() -> PinService:
    """Return cached pin service instance."""
    return PinService()
