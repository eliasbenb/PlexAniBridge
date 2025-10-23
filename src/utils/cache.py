"""Cache Utilities Module."""

from functools import wraps
from typing import Any

import aiocache
import cachetools


def glru_cache(maxsize: int | None = 128):
    """Function decorator to cache function results using an LRU cache.

    Unlike functools.lru_cache, this decorator can be used with any object,
    even if it's unhashable. The cache key is computed by hashing the input
    arguments using a recursive algorithm.

    Args:
        maxsize (int | None): Maximum number of items in the cache. Defaults to 128.

    Returns:
        Callable: Decorator function that caches the decorated function's results
    """
    if maxsize is None:
        maxsize = 2**32  # 'infinitely' large cache

    def decorator(func):
        @wraps(func)
        @cachetools.cached(cachetools.LRUCache(maxsize), key=generic_hash)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


def gttl_cache(maxsize: int | None = 128, ttl: int = 600):
    """Function decorator to cache function results using a TTL cache.

    Unlike functools.lru_cache, this decorator can be used with any object,
    even if it's unhashable. The cache key is computed by hashing the input
    arguments using a recursive algorithm.

    Args:
        maxsize (int | None): Maximum number of items in the cache. Defaults to 128.
        ttl (int | None): Time-to-live for cached items in seconds. Defaults to 600.
    """
    if maxsize is None:  # 'infinitely' large cache
        maxsize = 2**32

    def decorator(func):
        @wraps(func)
        @cachetools.cached(cachetools.TTLCache(maxsize, ttl), key=generic_hash)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


def gattl_cache(ttl: int = 60):
    """Decorator for functions to cache results using a generic, async-aware TTL cache.

    This decorator can be used with any object, even if it's unhashable,
    because it uses the generic_hash function to compute the cache key.

    It uses `aiocache` as the backend to ensure compatibility with async functions.

    Args:
        ttl (int): Time-to-live for cached items in seconds. Defaults to 60.
    """

    def decorator(func):
        # Create a unique alias for the cache configuration.
        cache_alias = f"galru_{func.__module__}.{func.__qualname__}_{id(func)}"

        aiocache.caches.add(cache_alias, {"cache": aiocache.Cache.MEMORY, "ttl": ttl})

        def key_builder_adapter(f, *args, **kwargs):
            return generic_hash(*args, **kwargs)

        @wraps(func)
        @aiocache.cached(alias=cache_alias, key_builder=key_builder_adapter)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def generic_hash(*args, **kwargs):
    """Recursively computes a hash for any Python object(s).

    If a single object is passed (and no keyword arguments), its hash is computed.
    If multiple positional and/or keyword arguments are passed, a combined hash
    is returned based on all of them.

    For built-in hashable objects, the built-in hash is used.
    For unhashable objects (e.g. lists, dicts, sets), they are converted into
    a hashable representation by processing their elements.
    """
    visited_ids = set()

    if not kwargs and len(args) == 1:
        return _generic_hash(args[0], visited_ids)
    else:
        args_hash = _generic_hash(args, visited_ids)
        kwargs_hash = _generic_hash(tuple(sorted(kwargs.items())), visited_ids)
        return hash((args_hash, kwargs_hash))


def _generic_hash(obj: Any, _visited_ids: set[int]) -> int:
    obj_id = id(obj)
    if obj_id in _visited_ids:
        return hash("<cycle>")

    _visited_ids.add(obj_id)
    try:
        h = hash(obj)
    except TypeError:
        if isinstance(obj, list | tuple):
            h = hash(tuple(_generic_hash(item, _visited_ids) for item in obj))
        elif isinstance(obj, set):
            h = hash(frozenset(_generic_hash(item, _visited_ids) for item in obj))
        elif isinstance(obj, dict):
            h = hash(
                tuple(
                    sorted(
                        (_generic_hash(k, _visited_ids), _generic_hash(v, _visited_ids))
                        for k, v in obj.items()
                    )
                )
            )
        elif hasattr(obj, "__dict__"):
            h = _generic_hash(obj.__dict__, _visited_ids)
        elif hasattr(obj, "__iter__"):
            h = hash(tuple(_generic_hash(item, _visited_ids) for item in obj))
        else:
            h = hash(str(obj))
    _visited_ids.remove(obj_id)
    return h
