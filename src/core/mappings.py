import json
from pathlib import Path
from typing import Any, TypeAlias
from urllib.parse import urljoin, urlparse

import requests
import tomlkit
import yaml
from tomlkit.exceptions import TOMLKitError

from src import __version__, log

AniMapDict: TypeAlias = dict[str, dict[str, Any]]


class MappingsClient:
    """Load mappings from files or URLs and merge them together."""

    SCHEMA_VERSION = "v2"
    CDN_URL = f"https://raw.githubusercontent.com/eliasbenb/PlexAniBridge-Mappings/{SCHEMA_VERSION}/mappings.json"
    MAPPING_FILES = [
        "mappings.custom.json",
        "mappings.custom.yaml",
        "mappings.custom.yml",
        "mappings.custom.toml",
    ]

    def __init__(self, data_path: Path) -> None:
        self.data_path = data_path
        self._loaded_sources: set[str] = set()

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": f"PlexAniBridge/{__version__}",
            }
        )

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

    def _dict_str_keys(self, d: dict[str, Any]) -> dict[str, Any]:
        """Ensure all keys in a dictionary are strings.

        Args:
            d (dict[str, Any]): Dictionary to convert

        Returns:
            dict[str, Any]: Dictionary with all keys as strings
        """
        if isinstance(d, dict):
            return {str(k): self._dict_str_keys(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [self._dict_str_keys(i) for i in d]
        else:
            return d

    def _resolve_path(self, include_path: str, parent_path: Path | str) -> str:
        """Resolve a path relative to the parent path.

        Args:
            include_path (str): Path to resolve
            parent_path (Path | str): Parent path to resolve against

        Returns:
            str: Resolved path
        """
        is_url = self._is_url(include_path)
        is_file = self._is_file(include_path)
        is_parent_url = self._is_url(str(parent_path))
        is_parent_file = self._is_file(parent_path)

        # Absolute URL or absolute path
        if is_url or (is_file and parent_path.is_absolute()):
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

    def _load_includes(
        self, includes: list[str], loaded_chain: set[str], parent: Path | str
    ) -> AniMapDict:
        """Load mappings from included files or URLs.

        Args:
            includes (list[str]): List of file paths or URLs to include
            loaded_chain (set[str]): Set of already loaded includes to prevent circular includes
            parent (Path | str): Parent path or URL to resolve relative paths against

        Returns:
            AniMapDict: Merged mappings from all included files
        """
        mappings = {}
        for include in includes:
            resolved_include = self._resolve_path(include, parent)

            if resolved_include in loaded_chain:
                log.warning(
                    f"{self.__class__.__name__}: Circular include detected: '{resolved_include}' has already been loaded in this chain"
                )
                continue
            if resolved_include in self._loaded_sources:
                log.info(
                    f"{self.__class__.__name__}: Skipping already loaded include: '{resolved_include}'"
                )
                continue

            new_loaded_chain = loaded_chain | {resolved_include}
            include_mappings = self._load_mappings(resolved_include, new_loaded_chain)
            mappings = self._deep_merge(include_mappings, mappings)
        return mappings

    def _load_mappings_file(self, file: str, loaded_chain: set[str]) -> AniMapDict:
        """Load mappings from a file.

        Args:
            file (str): Path to the file to load
            loaded_chain (set[str]): Set of already loaded includes to prevent circular includes

        Returns:
            AniMapDict: Mappings loaded from the file
        """
        mappings: AniMapDict = {}
        file_path = Path(file)

        try:
            if file_path.suffix == ".json":
                with file_path.open() as f:
                    mappings = json.load(f)
            elif file_path.suffix in [".yaml", ".yml"]:
                with file_path.open() as f:
                    mappings = self._dict_str_keys(yaml.safe_load(f))
            elif file_path.suffix == ".toml":
                with file_path.open() as f:
                    mappings = tomlkit.load(f)
        except (json.JSONDecodeError, yaml.YAMLError, TOMLKitError) as e:
            log.error(
                f"{self.__class__.__name__}: Error decoding file "
                f"{file_path.absolute().as_posix()}: {e}"
            )
        except Exception as e:
            log.error(
                f"{self.__class__.__name__}: Unexpected error reading file "
                f"{file_path.absolute().as_posix()}: {e}"
            )

        self._loaded_sources.add(file)

        return self._deep_merge(
            self._load_includes(mappings.get("$includes", []), loaded_chain, file_path),
            mappings,
        )

    def _load_mappings_url(self, url: str, loaded_chain: set[str]) -> AniMapDict:
        """Load mappings from a URL.

        Args:
            url (str): URL to load mappings from
            loaded_chain (set[str]): Set of already loaded includes to prevent circular includes

        Returns:
            AniMapDict: Mappings loaded from the URL
        """
        mappings: AniMapDict = {}
        try:
            raw_res = self.session.get(url)
            raw_res.raise_for_status()
            mappings = raw_res.json()
        except requests.RequestException as e:
            log.error(
                f"{self.__class__.__name__}: Error reaching mappings URL {url}: {e}"
            )
        except json.JSONDecodeError as e:
            log.error(
                f"{self.__class__.__name__}: Error decoding mappings from URL {url}: {e}"
            )
        except Exception as e:
            log.error(
                f"{self.__class__.__name__}: Unexpected error fetching mappings from URL {url}: {e}"
            )

        self._loaded_sources.add(url)

        return self._deep_merge(
            self._load_includes(mappings.get("$includes", []), loaded_chain, url),
            mappings,
        )

    def _load_mappings(self, src: str, loaded_chain: set[str] = None) -> AniMapDict:
        """Load mappings from a file or URL.

        Args:
            src (str): Path to the file or URL to load mappings from
            loaded_chain (set[str], optional): Set of already loaded includes to prevent circular includes. Defaults to None.

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
            return self._load_mappings_file(src, loaded_chain)
        elif self._is_url(src):
            log.info(
                f"{self.__class__.__name__}: Loading mappings from URL $$'{src}'$$"
            )
            return self._load_mappings_url(src, loaded_chain)
        else:
            log.warning(
                f"{self.__class__.__name__}: Invalid mappings source: '{src}', skipping"
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

    def load_mappings(self) -> AniMapDict:
        """Load mappings from files and URLs and merge them together.

        Returns:
            AniMapDict: Merged mappings
        """
        self._loaded_sources = set()

        existing_custom_mapping_files = [
            f for f in self.MAPPING_FILES if (self.data_path / f).exists()
        ]

        if existing_custom_mapping_files:
            custom_mappings_path = (
                (self.data_path / existing_custom_mapping_files[0])
                .absolute()
                .as_posix()
            )
            custom_mappings = self._load_mappings(custom_mappings_path)
        else:
            custom_mappings_path = ""
            custom_mappings = {}

        if len(existing_custom_mapping_files) > 1:
            log.warning(
                f"{self.__class__.__name__}: Found multiple custom mappings files: {existing_custom_mapping_files}. "
                f"Only one mappings file can be used at a time. Defaulting to $$'{custom_mappings_path}'$$"
            )

        db_mappings = self._load_mappings(self.CDN_URL)
        merged_mappings = self._deep_merge(db_mappings, custom_mappings)

        return {k: v for k, v in merged_mappings.items() if not k.startswith("$")}
