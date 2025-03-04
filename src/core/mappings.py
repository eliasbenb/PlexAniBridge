import json
from pathlib import Path
from typing import Any, TypeAlias

import requests
import tomlkit
import yaml
from tomlkit.exceptions import TOMLKitError

from src import log

AniMapDict: TypeAlias = dict[str, dict[str, Any]]


class MappingsClient:
    """Load mappings from files or URLs and merge them together."""

    SCHEMA_VERSION = "v2"
    CDN_URL = f"https://raw.githubusercontent.com/eliasbenb/PlexAniBridge-Mappings/{SCHEMA_VERSION}/mappings.json"
    SCHEMA_URL = f"https://cdn.statically.io/gh/eliasbenb/PlexAniBridge-Mappings/{SCHEMA_VERSION}/mappings.schema.json"
    MAPPING_FILES = [
        "mappings.custom.json",
        "mappings.custom.yaml",
        "mappings.custom.yml",
        "mappings.custom.toml",
    ]

    def __init__(self, data_path: Path) -> None:
        self.data_path = data_path
        self._loaded_sources: set[str] = set()

    def _load_includes(self, includes: list[str], loaded_chain: set[str]) -> AniMapDict:
        """Load mappings from included files or URLs.

        Args:
            includes (list[str]): List of file paths or URLs to include
            loaded_chain (set[str]): Set of already loaded includes to prevent circular includes

        Returns:
            AniMapDict: Merged mappings from all included files
        """
        res = {}
        for include in includes:
            if include in loaded_chain:
                log.warning(
                    f"{self.__class__.__name__}: Circular include detected: '{include}' has already been loaded in this chain"
                )
                continue
            if include in self._loaded_sources:
                log.info(
                    f"{self.__class__.__name__}: Skipping already loaded include: '{include}'"
                )
                continue

            new_loaded_chain = loaded_chain | {include}
            res = self._deep_merge(res, self._load_mappings(include, new_loaded_chain))
        return res

    def _load_mappings_file(self, file: Path, loaded_chain: set[str]) -> AniMapDict:
        """Load mappings from a file.

        Args:
            file (Path): Path to the file to load
            loaded_chain (set[str]): Set of already loaded includes to prevent circular includes

        Returns:
            AniMapDict: Mappings loaded from the file
        """
        res: AniMapDict = {}
        file_str = str(file)

        try:
            if file.suffix == ".json":
                with file.open() as f:
                    res = json.load(f)
            elif file.suffix in [".yaml", ".yml"]:
                with file.open() as f:
                    res = yaml.safe_load(f)
            elif file.suffix == ".toml":
                with file.open() as f:
                    res = tomlkit.load(f)
        except (json.JSONDecodeError, yaml.YAMLError, TOMLKitError) as e:
            log.error(f"{self.__class__.__name__}: Error decoding file {file}: {e}")
        except Exception as e:
            log.error(
                f"{self.__class__.__name__}: Unexpected error reading file {file}: {e}"
            )

        self._loaded_sources.add(file_str)

        includes = [
            include if Path(include).is_absolute() else str(file.parent / include)
            for include in res.get("$includes", [])
        ]
        return self._deep_merge(res, self._load_includes(includes, loaded_chain))

    def _load_mappings_url(self, url: str, loaded_chain: set[str]) -> AniMapDict:
        """Load mappings from a URL.

        Args:
            url (str): URL to load mappings from
            loaded_chain (set[str]): Set of already loaded includes to prevent circular includes

        Returns:
            AniMapDict: Mappings loaded from the URL
        """
        res: AniMapDict = {}
        try:
            raw_res = requests.get(url)
            raw_res.raise_for_status()
            res = raw_res.json()
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

        includes = res.get("$includes", [])
        return self._deep_merge(res, self._load_includes(includes, loaded_chain))

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

        if Path(src).is_file():
            log.info(
                f"{self.__class__.__name__}: Loading mappings from file $$'{src}'$$"
            )
            return self._load_mappings_file(Path(src), loaded_chain)
        elif src.startswith("http"):
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
            if key not in result or key == "tvdb_mappings":
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
        if not existing_custom_mapping_files:
            return {}

        custom_mappings_path = self.data_path / existing_custom_mapping_files[0]
        if len(existing_custom_mapping_files) > 1:
            log.warning(
                f"{self.__class__.__name__}: Found multiple custom mappings files: {existing_custom_mapping_files}. "
                f"Only one mappings file can be used at a time. Defaulting to $$'{custom_mappings_path}'$$"
            )

        custom_mappings = self._load_mappings(str(custom_mappings_path))
        db_mappings = self._load_mappings(self.CDN_URL)
        merged_mappings = self._deep_merge(db_mappings, custom_mappings)

        return {k: v for k, v in merged_mappings.items() if not k.startswith("$")}
