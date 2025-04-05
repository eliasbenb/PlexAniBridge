from time import sleep

import requests
import urllib3.exceptions
from limiter import Limiter  # type: ignore

from src import __version__, log

plex_community_limiter = Limiter(rate=300 / 60, capacity=30, jitter=True)


class PlexCommunityClient:
    API_URL = "https://community.plex.tv/api"

    def __init__(self, plex_token: str):
        self.plex_token = plex_token

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": f"PlexAniBridge/{__version__}",
                "X-Plex-Token": self.plex_token,
            }
        )

    def get_watch_activity(self, metadata_id: str) -> list:
        """Fetches only watch activity for a given metadata ID and returns a list of PlexAPI EpisodeHistory or MovieHistory objects.

        Args:
            metadata_id (str): The metadata ID to fetch watch activity for.

        Returns:
            list: A list of PlexAPI EpisodeHistory or MovieHistory objects.
        """
        query = """
        query GetWatchActivity($first: PaginationInt!, $after: String, $metadataID: ID) {
            activityFeed(
                first: $first
                after: $after
                metadataID: $metadataID
                types: [WATCH_HISTORY]
                includeDescendants: true
            ) {
                nodes {
                    ... on ActivityWatchHistory {
                        id
                        date
                        metadataItem {
                            id
                            type
                            title
                            index
                            parent {
                                id
                                type
                                title
                                index
                            }
                            grandparent {
                                id
                                type
                                title
                                index
                            }
                        }
                        userV2 {
                            id
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
        """

        res = []
        current_after = None
        while True:
            response = self._make_request(
                query,
                {"metadataID": metadata_id, "first": 50, "after": current_after},
                "GetWatchActivity",
            )

            data = response["data"]["activityFeed"]
            if not data or not data["nodes"]:
                break
            res.extend(data["nodes"])

            if not data["pageInfo"]["hasNextPage"]:
                break
            current_after = data["pageInfo"]["endCursor"]

        return res

    def get_reviews(self, metadata_id: str) -> str | None:
        """Fetches reviews for a given metadata ID.

        Args:
            metadata_id (str): The metadata ID to fetch reviews for

        Returns:
            str: The review message, or None if no review is found
        """
        query = """
        query GetReview($metadataID: ID!) {
            metadataReviewV2(metadata: {id: $metadataID}) {
                ... on ActivityReview {
                    message
                }
                ... on ActivityWatchReview {
                    message
                }
            }
        }
        """

        response = self._make_request(query, {"metadataID": metadata_id}, "GetReview")
        data = response["data"]["metadataReviewV2"]

        if not data or "message" not in data:
            return None
        return data["message"]

    def _make_request(
        self,
        query: str,
        variables: dict | str | None = None,
        operation_name: str | None = None,
        retry_count: int = 0,
    ) -> dict:
        """Makes a rate-limited request to the Plex Community API.

        Handles rate limiting, authentication, and automatic retries for
        rate limit exceeded responses.

        Args:
            query (str): GraphQL query string
            variables (dict | str | None): Variables for the GraphQL query
            operation_name (str | None): The operation name for the GraphQL query
            retry_count (int): The number of times the request has been retried

        Returns:
            dict: JSON response from the API

        Raises:
            requests.exceptions.HTTPError: If the request fails for any reason other than rate limiting
        """
        if retry_count >= 3:
            raise requests.exceptions.HTTPError("Failed to make request after 3 tries")

        try:
            response = self.session.post(
                self.API_URL,
                json={
                    "query": query,
                    "variables": variables,
                    "operationName": operation_name,
                },
            )
        except (
            requests.exceptions.RequestException,
            urllib3.exceptions.ProtocolError,
        ):
            log.error(
                f"{self.__class__.__name__}: Connection error while making request to the Plex Community API"
            )
            sleep(1)
            return self._make_request(
                query=query, variables=variables, retry_count=retry_count + 1
            )

        if response.status_code == 429:  # Handle rate limit retries
            retry_after = int(response.headers.get("Retry-After", 60))
            log.warning(
                f"{self.__class__.__name__}: Rate limit exceeded, waiting {retry_after} seconds"
            )
            sleep(retry_after + 1)
            return self._make_request(
                query,
                variables=variables,
                operation_name=operation_name,
                retry_count=retry_count,
            )
        elif response.status_code == 502:  # Bad Gateway
            log.warning(
                f"{self.__class__.__name__}: Received 502 Bad Gateway, retrying"
            )
            sleep(1)
            return self._make_request(
                query,
                variables=variables,
                operation_name=operation_name,
                retry_count=retry_count + 1,
            )

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            log.error(
                f"{self.__class__.__name__}: Failed to make request to the Plex Community API"
            )
            log.error(f"\t\t{response.text}")
            raise e

        return response.json()
