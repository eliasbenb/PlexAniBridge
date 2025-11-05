"""GUID parsing strategies for different media services."""

from typing import List

from .base import GuidParsingStrategy
from .imdb import ImdbGuidParsingStrategy
from .tmdb import TmdbGuidParsingStrategy
from .tvdb import TvdbGuidParsingStrategy

__all__ = [
    "GuidParsingStrategy",
    "ImdbGuidParsingStrategy",
    "TmdbGuidParsingStrategy",
    "TvdbGuidParsingStrategy",
    "get_default_strategies",
]


def get_default_strategies() -> List[GuidParsingStrategy]:
    """Returns the default list of GUID parsing strategies.

    This function provides dependency injection capability by allowing
    the list of strategies to be dynamically configured or extended.

    Returns:
        List[GuidParsingStrategy]: List of default parsing strategies.
    """
    return [
        TvdbGuidParsingStrategy(),
        TmdbGuidParsingStrategy(),
        ImdbGuidParsingStrategy(),
    ]