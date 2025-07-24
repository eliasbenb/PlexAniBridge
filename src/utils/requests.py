"""Selective SSL Verification for Requests Module."""

import warnings
from urllib.parse import urlparse

import requests
from urllib3.exceptions import InsecureRequestWarning


class SelectiveVerifySession(requests.Session):
    """Session that selectively disables SSL verification for whitelisted domains."""

    def __init__(self, whitelist=None) -> None:
        """Initialize the session with a whitelist of domains."""
        super().__init__()
        self.whitelist = set(whitelist or [])

    def request(self, method, url, *_, **kwargs):
        """Override the request method to selectively disable SSL verification."""
        domain = urlparse(url).hostname
        # Disable SSL verification for whitelisted domains
        if domain in self.whitelist:
            kwargs["verify"] = False
            # Suppress SSL warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", InsecureRequestWarning)
                return super().request(method, url, **kwargs)
        return super().request(method, url, *_, **kwargs)
