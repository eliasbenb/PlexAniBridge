"""Mappings Client Module."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, ClassVar, TypeAlias
from urllib.parse import urljoin, urlparse

import aiohttp
import yaml

from src import __version__, log

__all__ = ["AniMapDict", "MappingsClient"]

AniMapDict: TypeAlias = dict[str, dict[str, Any]]


class MappingsClient:
    """Load mappings from files or URLs and merge them together."""

    MAPPING_FILES: ClassVar[list[str]] = [
        "mappings.custom.yaml",
        "mappings.custom.yml",
        "mappings.custom.json",
    ]

    def __init__(self, data_path: Path, upstream_url: str | None) -> None:
        """Initialize the MappingsClient with the data path.

        Args:
            data_path (Path): Path to the data directory for storing mappings and cache
                              files.
            upstream_url (str | None): URL to the upstream mappings source JSON or YAML
                                      file. If None, no upstream mappings will be used.
        """
        self.data_path = data_path
        self.upstream_url = upstream_url
        self._loaded_sources: set[str] = set()
        self._provenance: dict[str, list[str]] = {}
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": f"PlexAniBridge/{__version__}",
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> MappingsClient:
        """Context manager enter method.

        Returns:
            MappingsClient: The initialized mappings client instance.
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit method.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Traceback object if an exception occurred.
        """
        await self.close()

    def _is_file(self, src: str) -> bool:
        """Check if the source is a file.

        Args:
            src (str): Source to check

        Returns:
            bool: True if the source is a file, False otherwise
        """
        try:
            parsed = Path(src)
        except Exception:
            return False
        return parsed.is_file()

    def _is_url(self, src: str) -> bool:
        """Check if the source is a URL.

        Args:
            src (str): Source to check

        Returns:
            bool: True if the source is a URL, False otherwise
        """
        parsed = urlparse(src)
        return bool(parsed.scheme) and bool(parsed.netloc)

    def _dict_str_keys(self, d: dict | list) -> Any:
        """Ensure all keys in a dictionary are strings.

        Args:
            d (dict | list): Dictionary or list to convert

        Returns:
            dict | list: Dictionary with all keys as strings or a list
        """
        if isinstance(d, dict):
            return {str(k): self._dict_str_keys(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [self._dict_str_keys(i) for i in d]
        else:
            return d

    def _resolve_path(self, include_path: str, parent_path: str) -> str:
        """Resolve a path relative to the parent path.

        Args:
            include_path (str): Path to resolve
            parent_path (str): Parent path to resolve against

        Returns:
            str: Resolved path
        """
        is_url = self._is_url(include_path)
        is_file = self._is_file(include_path)
        is_parent_url = self._is_url(str(parent_path))
        is_parent_file = self._is_file(parent_path)

        # Absolute URL or absolute path
        if is_url or (is_file and Path(parent_path).is_absolute()):
            return include_path
        # Relative URL
        if is_parent_url:
            return urljoin(parent_path, include_path)
        # Relative path
        if is_parent_file:
            parent_dir = Path(parent_path).parent
            resolved_path = (parent_dir / include_path).resolve()
            return resolved_path.as_posix()
        # Invalid path
        return include_path

    async def _load_includes(
        self, includes: list[str], loaded_chain: set[str], parent: str
    ) -> AniMapDict:
        """Load mappings from included files or URLs.

        Args:
            includes (list[str]): List of file paths or URLs to include
            loaded_chain (set[str]): Set of already loaded includes to prevent circular
                                     includes
            parent (str): Parent path or URL to resolve relative paths against

        Returns:
            AniMapDict: Merged mappings from all included files
        """
        mappings: dict[str, dict[str, Any]] = {}
        for include in includes:
            resolved_include = self._resolve_path(include, parent)

            if resolved_include in loaded_chain:
                log.warning(
                    f"{self.__class__.__name__}: Circular include detected: "
                    f"$$'{resolved_include}'$$ has already been loaded in this chain"
                )
                continue
            if resolved_include in self._loaded_sources:
                log.info(
                    f"{self.__class__.__name__}: Skipping already loaded include: "
                    f"$$'{resolved_include}'$$"
                )
                continue

            new_loaded_chain = loaded_chain | {resolved_include}
            include_mappings = await self._load_mappings(
                resolved_include, new_loaded_chain
            )
            mappings = self._deep_merge(include_mappings, mappings)
        return mappings

    async def _load_mappings_file(
        self, file: str, loaded_chain: set[str]
    ) -> AniMapDict:
        """Load mappings from a file.

        Args:
            file (str): Path to the file to load
            loaded_chain (set[str]): Set of already loaded includes to prevent circular
                                     includes

        Returns:
            AniMapDict: Mappings loaded from the file
        """
        mappings: AniMapDict = {}
        file_path = Path(file)

        try:
            match file_path.suffix:
                case ".json":
                    with file_path.open() as f:
                        mappings = json.load(f)
                case ".yaml" | ".yml":
                    with file_path.open() as f:
                        mappings = self._dict_str_keys(yaml.safe_load(f))
        except (json.JSONDecodeError, yaml.YAMLError):
            log.error(
                f"{self.__class__.__name__}: Error decoding file "
                f"$$'{file_path.resolve()!s}'$$",
                exc_info=True,
            )
        except Exception:
            log.error(
                f"{self.__class__.__name__}: Unexpected error reading file "
                f"$$'{file_path.resolve()!s}'$$",
                exc_info=True,
            )

        self._loaded_sources.add(file)

        if not mappings:
            log.warning(
                f"{self.__class__.__name__}: No mappings found in file "
                f"$$'{file_path.resolve()!s}'$$"
            )
            return {}

        includes: list[str] = []
        includes_value: dict | list = mappings.get("$includes", [])
        if isinstance(includes_value, list):
            includes = [str(item) for item in includes_value]
        else:
            log.warning(
                f"{self.__class__.__name__}: The $includes key in "
                f"$$'{file_path.resolve()!s}'$$ is not a list, ignoring all entries"
            )

        merged = self._deep_merge(
            await self._load_includes(includes, loaded_chain, str(file_path)),
            mappings,
        )

        # Record provenance for keys present in this file or its includes
        for key in merged:
            if not str(key).startswith("$"):
                k = str(key)
                src = str(file_path)
                lst = self._provenance.setdefault(k, [])
                if src not in lst:
                    lst.append(src)
        return merged

    async def _load_mappings_url(
        self, url: str, loaded_chain: set[str], retry_count: int = 0
    ) -> AniMapDict:
        """Load mappings from a URL.

        Args:
            url (str): URL to load mappings from
            loaded_chain (set[str]): Set of already loaded includes to prevent circular
                                     includes
            retry_count (int): Number of retries to attempt (default: 0)

        Returns:
            AniMapDict: Mappings loaded from the URL
        """
        mappings: AniMapDict = {}
        mappings_raw: str = ""
        session = await self._get_session()

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                mappings_raw = await response.text()
        except (TimeoutError, aiohttp.ClientError):
            if retry_count < 2:
                log.warning(
                    f"{self.__class__.__name__}: Error reaching mappings URL "
                    f"$$'{url}'$$, retrying...",
                    exc_info=True,
                )
                await asyncio.sleep(1)
                return await self._load_mappings_url(url, loaded_chain, retry_count + 1)
            log.error(
                f"{self.__class__.__name__}: Error reaching mappings URL $$'{url}'$$",
                exc_info=True,
            )
        except Exception:
            log.error(
                f"{self.__class__.__name__}: Unexpected error fetching mappings from "
                f"URL $$'{url}'$$",
                exc_info=True,
            )

        try:
            match Path(url).suffix:
                case ".json":
                    mappings = json.loads(mappings_raw)
                case ".yaml" | ".yml":
                    mappings = self._dict_str_keys(yaml.safe_load(mappings_raw))
                case _:
                    log.warning(
                        f"{self.__class__.__name__}: Unknown file type for URL "
                        f"$$'{url}'$$, defaulting to JSON parsing"
                    )
                    mappings = json.loads(mappings_raw)
        except (json.JSONDecodeError, yaml.YAMLError):
            log.error(
                f"{self.__class__.__name__}: Error decoding file $$'{url!s}'$$",
                exc_info=True,
            )
        except Exception:
            log.error(
                f"{self.__class__.__name__}: Unexpected error reading file "
                f"$$'{url!s}'$$",
                exc_info=True,
            )

        self._loaded_sources.add(url)

        if not mappings:
            log.warning(
                f"{self.__class__.__name__}: No mappings found in URL $$'{url}'$$"
            )
            return {}

        includes: list[str] = []
        includes_value: dict | list = mappings.get("$includes", [])
        if isinstance(includes_value, list):
            includes = [str(item) for item in includes_value]
        else:
            log.warning(
                f"{self.__class__.__name__}: $includes in {url} is not a list, ignoring"
            )

        merged = self._deep_merge(
            await self._load_includes(includes, loaded_chain, url),
            mappings,
        )

        # Record provenance for keys present at this URL or its includes
        for key in merged:
            if not str(key).startswith("$"):
                k = str(key)
                src = str(url)
                lst = self._provenance.setdefault(k, [])
                if src not in lst:
                    lst.append(src)

        return merged

    async def _load_mappings(
        self, src: str, loaded_chain: set[str] | None = None
    ) -> AniMapDict:
        """Load mappings from a file or URL.

        Args:
            src (str): Path to the file or URL to load mappings from
            loaded_chain (set[str]): Set of already loaded includes to prevent
                                     circular includes (default: empty set)

        Returns:
            AniMapDict: Mappings loaded from the file or URL
        """
        if loaded_chain is None:
            loaded_chain = set()
        loaded_chain = loaded_chain | {src}

        if self._is_file(src):
            log.info(
                f"{self.__class__.__name__}: Loading mappings from file $$'{src}'$$"
            )
            return await self._load_mappings_file(src, loaded_chain)
        elif self._is_url(src):
            log.info(
                f"{self.__class__.__name__}: Loading mappings from URL $$'{src}'$$"
            )
            return await self._load_mappings_url(src, loaded_chain)
        else:
            log.warning(
                f"{self.__class__.__name__}: Invalid mappings source: $$'{src}'$$, "
                f"skipping"
            )
            return {}

    def _deep_merge(self, d1: AniMapDict, d2: AniMapDict) -> AniMapDict:
        """Recursively merge two dictionaries.

        Special handling for "tvdb_mappings" key to prevent overwriting.

        Args:
            d1 (AniMapDict): First dictionary
            d2 (AniMapDict): Second dictionary

        Returns:
            AniMapDict: Merged dictionary
        """
        result = d1.copy()

        for key, value in d2.items():
            if key == "tvdb_mappings" or key not in result:
                result[key] = value
            elif isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    async def load_mappings(self) -> AniMapDict:
        """Load mappings from files and URLs and merge them together.

        Loads custom mappings from local files (if they exist) and default mappings
        from the CDN URL, then merges them with custom mappings taking precedence.
        Filters out any keys starting with '$' from the final result.

        Returns:
            AniMapDict: Merged mappings with system keys removed
        """
        self._loaded_sources = set()
        self._provenance = {}

        if self.upstream_url is not None:
            log.debug(
                f"{self.__class__.__name__}: Using upstream mappings URL "
                f"$$'{self.upstream_url}'$$"
            )
            db_mappings = await self._load_mappings(str(self.upstream_url))
        else:
            log.debug(
                f"{self.__class__.__name__}: No upstream mappings URL configured, "
                f"skipping"
            )
            db_mappings = {}

        existing_custom_mapping_files = [
            f for f in self.MAPPING_FILES if (self.data_path / f).exists()
        ]

        if existing_custom_mapping_files:
            custom_mappings_path = str(
                (self.data_path / existing_custom_mapping_files[0]).resolve()
            )
            custom_mappings = await self._load_mappings(custom_mappings_path)
        else:
            custom_mappings_path = ""
            custom_mappings = {}

        if len(existing_custom_mapping_files) > 1:
            log.warning(
                f"{self.__class__.__name__}: Found multiple custom mappings files: "
                f"{existing_custom_mapping_files}. Only one mappings file can be used "
                f"at a time. Defaulting to $$'{custom_mappings_path}'$$"
            )

        merged_mappings = self._deep_merge(db_mappings, custom_mappings)

        return {k: v for k, v in merged_mappings.items() if not k.startswith("$")}

    def get_provenance(self) -> dict[int, list[str]]:
        """Return a copy of the provenance map collected during the last load.

        Returns:
            dict[int, list[str]]: Mapping of anilist_id to list of unique sources
        """
        result: dict[int, list[str]] = {}
        for k, sources in self._provenance.items():
            try:
                anilist_id = int(k)
            except ValueError:
                log.warning(
                    f"{self.__class__.__name__}: Skipping invalid anilist_id in "
                    f"provenance: $$'{k}'$$"
                )
                continue
            result[anilist_id] = [str(s) for s in sources]

        return result
