from collections import deque
from time import sleep, time

from src import log


class RateLimiter:
    def __init__(self, log_name: str, requests_per_minute: int = 90):
        self.log_name = log_name
        self.requests_per_minute = requests_per_minute

        self.request_times = deque(maxlen=requests_per_minute)

    def wait_if_needed(self):
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

        self.request_times.append(now)
