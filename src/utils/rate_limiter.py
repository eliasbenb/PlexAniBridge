from collections import deque
from time import sleep, time

from src import log


class RateLimiter:
    """Rate limiter that sleeps if the rate limit is hit

    The rate limiter keeps track of all requests made in the last minute.
    When the rate limit is hit in the one minute window, the rate limiter will sleep.

    The rate limiter also enforces a minimum time between requests to prevent bursting.

    The rate limiter relies on the developer to call `wait_if_needed` before making a request.
    """

    def __init__(self, log_name: str, requests_per_minute: int = 90) -> None:
        self.log_name = log_name
        self.requests_per_minute = requests_per_minute
        self.min_request_interval = 60 / requests_per_minute

        self.request_times = deque(maxlen=requests_per_minute)
        self.last_request_time = 0

    def wait_if_needed(self) -> None:
        """Sleeps if the rate limit is hit or to maintain minimum interval between requests"""
        now = time()

        time_since_last_request = now - self.last_request_time
        if (
            self.last_request_time > 0
            and time_since_last_request < self.min_request_interval
        ):
            sleep_time = self.min_request_interval - time_since_last_request
            sleep(sleep_time)
            now = time()

        while self.request_times and now - self.request_times[0] > 60:
            self.request_times.popleft()

        if len(self.request_times) >= self.requests_per_minute:
            sleep_time = 60 - (now - self.request_times[0])
            if sleep_time > 0:
                log.debug(
                    f"{self.log_name}: Rate limit hit, sleeping for {sleep_time:.2f} seconds"
                )
                sleep(sleep_time)
                now = time()

        self.request_times.append(now)
        self.last_request_time = now
