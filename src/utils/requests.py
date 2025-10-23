"""Selective SSL Verification for Requests Module."""

import warnings
from urllib.parse import urlparse

import requests
from urllib3.exceptions import InsecureRequestWarning

from src import log


class SelectiveVerifySession(requests.Session):
    """Session that selectively disables SSL verification for whitelisted domains."""

    def __init__(self, whitelist=None) -> None:
        """Initialize the session with a whitelist of domains."""
        super().__init__()
        self.whitelist = set(whitelist or [])
        if self.whitelist:
            log.debug(
                "SSL verify disabled for domains: "
                + ", ".join([f"$$'{d}'$$" for d in sorted(self.whitelist)])
            )

    def request(self, method, url, *_, **kwargs):
        """Override the request method to selectively disable SSL verification."""
        domain = urlparse(url).hostname
        # Disable SSL verification for whitelisted domains
        if domain in self.whitelist:
            kwargs["verify"] = False
            # Suppress SSL warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", InsecureRequestWarning)
                try:
                    return super().request(method, url, **kwargs)
                except Exception as e:
                    log.error(
                        (f"Error during request to $$'{domain}'$$: {e}"),
                        exc_info=True,
                    )
                    raise
        return super().request(method, url, *_, **kwargs)
