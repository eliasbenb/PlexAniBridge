"""TMDB GUID parsing strategy."""

from typing import Optional

from .base import GuidParsingStrategy


class TmdbGuidParsingStrategy(GuidParsingStrategy):
    """Strategy for parsing TMDB GUIDs."""

    def parse(self, guid_id: str) -> Optional[tuple[str, int]]:
        if (
            guid_id.startswith("tmdb://")
            or guid_id.startswith("com.plexapp.agents.tmdb://")
            or guid_id.startswith("com.plexapp.agents.themoviedb://")
        ):
            id_part = guid_id.split("://")[1].split("?")[0]
            try:
                return "tmdb", int(id_part)
            except ValueError:
                return None
        return None