import warnings
from urllib.parse import urlparse

import requests
from urllib3.exceptions import InsecureRequestWarning


class SelectiveVerifySession(requests.Session):
    def __init__(self, whitelist=None):
        super().__init__()
        self.whitelist = set(whitelist or [])

    def request(self, method, url, **kwargs):
        domain = urlparse(url).hostname
        # Disable SSL verification for whitelisted domains
        if domain in self.whitelist:
            kwargs["verify"] = False
            # Suppress SSL warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", InsecureRequestWarning)
                return super().request(method, url, **kwargs)
        return super().request(method, url, **kwargs)
