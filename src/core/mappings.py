import json
from pathlib import Path
from typing import Any, TypeAlias

import requests
import toml
import yaml

from src import log

AniMapDict: TypeAlias = dict[str, dict[str, Any]]


class MappingsClient:
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

    def _prepare_includes(self, parent: Path, includes: list[str]) -> list[str]:
        return [str(parent / include) for include in includes]

    def _load_includes(self, includes: list[str]) -> AniMapDict:
        res = {}
        for include in includes:
            res = self._deep_merge(res, self._load_mappings(include))
        return res

    def _load_mappings_file(self, file: Path) -> AniMapDict:
        res: AniMapDict = {}
        try:
            if file.suffix == ".json":
                with file.open() as f:
                    res = json.load(f)
            elif file.suffix in [".yaml", ".yml"]:
                with file.open() as f:
                    res = yaml.safe_load(f)
            elif file.suffix == ".toml":
                with file.open() as f:
                    res = toml.load(f)
        except (json.JSONDecodeError, yaml.YAMLError, toml.TomlDecodeError) as e:
            log.error(f"Error decoding file {file}: {e}")
        except Exception as e:
            log.error(f"Unexpected error reading file {file}: {e}")

        includes = [str(file.parent / include) for include in res.get("$includes", [])]
        return self._deep_merge(res, self._load_includes(includes))

    def _load_mappings_url(self, url: str) -> AniMapDict:
        res: AniMapDict = {}
        try:
            raw_res = requests.get(url)
            raw_res.raise_for_status()
            res = raw_res.json()
        except requests.RequestException as e:
            log.error(f"Error reaching mappings URL {url}: {e}")
        except json.JSONDecodeError as e:
            log.error(f"Error decoding mappings from URL {url}: {e}")
        except Exception as e:
            log.error(f"Unexpected error fetching mappings from URL {url}: {e}")

        includes = res.get("$includes", [])
        return self._deep_merge(res, self._load_includes(includes))

    def _load_mappings(self, src: str) -> AniMapDict:
        if Path(src).is_file():
            log.info(f"Loading mappings from file $$'{src}'$$")
            return self._load_mappings_file(Path(src))
        elif src.startswith("http"):
            log.info(f"Loading mappings from URL $$'{src}'$$")
            return self._load_mappings_url(src)
        else:
            raise ValueError(f"Invalid mappings source: '{src}'")

    def _deep_merge(self, d1: AniMapDict, d2: AniMapDict) -> AniMapDict:
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
