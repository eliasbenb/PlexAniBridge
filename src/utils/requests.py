from urllib.parse import urlparse

import requests


class SelectiveVerifySession(requests.Session):
    def __init__(self, whitelist=None):
        super().__init__()
        self.whitelist = set(whitelist or [])

    def request(self, method, url, **kwargs):
        domain = urlparse(url).hostname
        if domain in self.whitelist:
            kwargs["verify"] = False
        return super().request(method, url, **kwargs)
