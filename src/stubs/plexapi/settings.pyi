from typing import Any
from xml.etree.ElementTree import Element

from plexapi.base import PlexObject
from plexapi.server import PlexServer

class Settings(PlexObject):
    def __init__(
        self, server: PlexServer, data: Element, initpath: str | None = None
    ) -> None: ...
    def __getattr__(self, attr): ...  # TODO: type
    def __setattr__(self, attr, value): ...  # TODO: type
    def all(self) -> list[Setting]: ...
    def get(self, id) -> Setting: ...
    def groups(self) -> dict[str, list[Setting]]: ...
    def group(self, group) -> list[Setting]: ...
    def save(self) -> None: ...

class Setting(PlexObject):
    TYPES: dict  # TODO: type
    type: str
    advanced: bool
    default: Any
    enumValues: Any
    group: str
    hidden: bool
    id: str
    label: str
    option: str
    secure: bool
    summary: str
    value: Any
    _setValue: Any = None
    def set(self, value: Any) -> None: ...
    def toUrl(self) -> str: ...

class Preferences(Setting):
    FILTER: str
