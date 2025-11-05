"""Base GUID parsing strategy."""

from abc import ABC, abstractmethod
from typing import Optional, Union


class GuidParsingStrategy(ABC):
    """Abstract strategy for parsing GUIDs from different services."""

    @abstractmethod
    def parse(self, guid_id: str) -> Optional[tuple[str, Union[int, str]]]:
        """Parses a GUID ID and returns the attribute name and value.

        Args:
            guid_id (str): The GUID ID to parse.

        Returns:
            tuple[str, int | str] | None: Tuple of (attribute_name, value) or None if not applicable.
        """
        pass