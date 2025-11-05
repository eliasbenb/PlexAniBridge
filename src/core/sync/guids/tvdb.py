"""TVDB GUID parsing strategy."""

from typing import Optional

from .base import GuidParsingStrategy


class TvdbGuidParsingStrategy(GuidParsingStrategy):
    """Strategy for parsing TVDB GUIDs."""

    def parse(self, guid_id: str) -> Optional[tuple[str, int]]:
        if guid_id.startswith("tvdb://") or guid_id.startswith("com.plexapp.agents.thetvdb://"):
            id_part = guid_id.split("://")[1].split("?")[0]
            try:
                return "tvdb", int(id_part)
            except ValueError:
                return None
        return None