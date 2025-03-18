from functools import wraps

from cachetools import LRUCache, TTLCache, cached


def generic_lru_cache(maxsize=128):
    def decorator(func):
        @wraps(func)
        @cached(LRUCache(maxsize), key=generic_hash)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


def generic_ttl_cache(maxsize=128, ttl=600):
    if maxsize is None:
        maxsize = 2**32

    def decorator(func):
        @wraps(func)
        @cached(TTLCache(maxsize, ttl), key=generic_hash)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


def generic_hash(*args, **kwargs):
    """
    Recursively computes a hash for any Python object(s).

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


def _generic_hash(obj, _visited_ids):
    obj_id = id(obj)
    if obj_id in _visited_ids:
        return hash("<cycle>")

    _visited_ids.add(obj_id)
    try:
        h = hash(obj)
    except TypeError:
        if isinstance(obj, (list, tuple)):
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
