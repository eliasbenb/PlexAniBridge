from functools import cache, wraps
from typing import Any, Callable


def user_cache(func: Callable[..., Any]) -> Callable[..., Any]:
    """A cache decorator that includes the user ID in the cache key.

    Wraps functools.cache to include the user ID in the cache key,
    ensuring different users have separate cache entries.

    Args:
        func (Callable[..., Any]): The function to wrap.
    Returns:
        Callable[..., Any]: The wrapped function.
    """

    @wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        user_id = (
            self.user.id if hasattr(self, "user") and hasattr(self.user, "id") else None
        )
        return cache(lambda user_id, s, *a, **kw: func(s, *a, **kw))(
            user_id, self, *args, **kwargs
        )

    return wrapper
