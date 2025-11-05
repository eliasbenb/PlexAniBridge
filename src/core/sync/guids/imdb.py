"""IMDB GUID parsing strategy."""

from typing import Optional

from .base import GuidParsingStrategy


class ImdbGuidParsingStrategy(GuidParsingStrategy):
    """Strategy for parsing IMDB GUIDs."""

    def parse(self, guid_id: str) -> Optional[tuple[str, str]]:
        if guid_id.startswith("imdb://") or guid_id.startswith("com.plexapp.agents.imdb://"):
            id_part = guid_id.split("://")[1].split("?")[0]
            return "imdb", id_part
        return None