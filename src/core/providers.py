"""Provider loader helpers."""

from collections.abc import Iterable
from importlib import import_module

from anibridge.library import LibraryProvider
from anibridge.library import provider_registry as library_registry
from anibridge.list import ListProvider
from anibridge.list import provider_registry as list_registry

from src.config.settings import AniBridgeConfig, AniBridgeProfileConfig
from src.exceptions import ProfileConfigError

__all__ = [
    "build_library_provider",
    "build_list_provider",
]

_DEFAULT_LIBRARY_PROVIDER_MODULES: tuple[str, ...] = (
    "anibridge_plex_provider.library",
)
_DEFAULT_LIST_PROVIDER_MODULES: tuple[str, ...] = (
    "anibridge_anilist_provider.list",
    "anibridge_mal_provider.list",
)
_LOADED_MODULES: set[str] = set()


def _import_modules(modules: Iterable[str]) -> None:
    """Import provider modules, ensuring each module loads only once."""
    for module in modules:
        if not module or module in _LOADED_MODULES:
            continue
        import_module(module)
        _LOADED_MODULES.add(module)


def _collect_module_overrides(config: AniBridgeConfig) -> set[str]:
    """Gather module names requested globally and by the profile."""
    modules: set[str] = set(config.provider_modules or [])
    if not config.provider_modules:
        return modules
    modules.update(config.provider_modules)
    return modules


def build_library_provider(profile: AniBridgeProfileConfig) -> LibraryProvider:
    """Instantiate the configured library provider for the profile.

    Args:
        profile (AniBridgeProfileConfig): The profile configuration.

    Returns:
        LibraryProvider: The instantiated library provider.
    """
    _import_modules(_collect_module_overrides(profile.parent))

    namespace = profile.library_provider
    config = profile.library_provider_config.get(namespace)

    try:
        return library_registry.create(namespace, config=config)
    except LookupError as exc:
        raise ProfileConfigError(
            f"No library provider registered for namespace '{namespace}'. "
            "Ensure the provider package is installed and listed under "
            "provider_modules."
        ) from exc


def build_list_provider(profile: AniBridgeProfileConfig) -> ListProvider:
    """Instantiate the configured list provider for the profile.

    Args:
        profile (AniBridgeProfileConfig): The profile configuration.

    Returns:
        ListProvider: The instantiated list provider.
    """
    _import_modules(_collect_module_overrides(profile.parent))

    namespace = profile.list_provider
    config = profile.list_provider_config.get(namespace)

    try:
        return list_registry.create(namespace, config=config)
    except LookupError as exc:
        raise ProfileConfigError(
            f"No list provider registered for namespace '{namespace}'. "
            "Ensure the provider package is installed and listed under "
            "provider_modules."
        ) from exc


# Pre-import default provider modules at factory load time
_import_modules(_DEFAULT_LIBRARY_PROVIDER_MODULES + _DEFAULT_LIST_PROVIDER_MODULES)
