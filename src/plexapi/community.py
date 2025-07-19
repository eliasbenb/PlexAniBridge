"""Plex Community Client Module."""

import asyncio
from typing import Any

import aiohttp
from limiter import Limiter

from src import __version__, log

plex_community_limiter = Limiter(rate=300 / 60, capacity=30, jitter=True)


class PlexCommunityClient:
    """Client for interacting with the Plex Community API."""

    API_URL = "https://community.plex.tv/api"

    def __init__(self, plex_token: str) -> None:
        """Initialize the PlexCommunityClient with a Plex token.

        Args:
            plex_token (str): The Plex token for authentication.
        """
        self.plex_token = plex_token
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": f"PlexAniBridge/{__version__}",
                "X-Plex-Token": self.plex_token,
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> "PlexCommunityClient":
        """Context manager enter method.

        Returns:
            PlexCommunityClient: The client instance
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit method.

        Args:
            exc_type: Exception type
            exc_val: Exception value
            exc_tb: Exception traceback
        """
        await self.close()

    async def get_watch_activity(self, metadata_id: str) -> list:
        """Get watch activity from the Plex Community API.

        Fetches only watch activity for a given metadata ID and returns a list of
        PlexAPI EpisodeHistory or MovieHistory objects.

        Args:
            metadata_id (str): The metadata ID to fetch watch activity for.

        Returns:
            list: A list of PlexAPI EpisodeHistory or MovieHistory objects.
        """
        query = """
        query GetWatchActivity(
            $first: PaginationInt!, $after: String, $metadataID: ID
        ) {
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
            response = await self._make_request(
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

    async def get_reviews(self, metadata_id: str) -> str | None:
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

        response = await self._make_request(
            query, {"metadataID": metadata_id}, "GetReview"
        )
        data = response["data"]["metadataReviewV2"]

        if not data or "message" not in data:
            return None
        return data["message"]

    @plex_community_limiter()
    async def _make_request(
        self,
        query: str,
        variables: dict[str, Any] | str | None = None,
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
            aiohttp.ClientError: If the request fails for any reason other than rate
                                 limiting.
        """
        if retry_count >= 3:
            raise aiohttp.ClientError("Failed to make request after 3 tries")

        session = await self._get_session()

        try:
            async with session.post(
                self.API_URL,
                json={
                    "query": query,
                    "variables": variables,
                    "operationName": operation_name,
                },
            ) as response:
                if response.status == 429:  # Handle rate limit retries
                    retry_after = int(response.headers.get("Retry-After", 60))
                    log.warning(
                        f"{self.__class__.__name__}: Rate limit exceeded, waiting "
                        f"{retry_after} seconds"
                    )
                    await asyncio.sleep(retry_after + 1)
                    return await self._make_request(
                        query=query,
                        variables=variables,
                        operation_name=operation_name,
                        retry_count=retry_count,
                    )
                elif response.status == 502:  # Bad Gateway
                    log.warning(
                        f"{self.__class__.__name__}: Received 502 Bad Gateway, retrying"
                    )
                    await asyncio.sleep(1)
                    return await self._make_request(
                        query=query,
                        variables=variables,
                        operation_name=operation_name,
                        retry_count=retry_count + 1,
                    )

                try:
                    response.raise_for_status()
                except aiohttp.ClientResponseError as e:
                    log.error(
                        f"{self.__class__.__name__}: Failed to make request to the "
                        f"Plex Community API"
                    )
                    response_text = await response.text()
                    log.error(f"\t\t{response_text}")
                    raise e

                return await response.json()

        except (aiohttp.ClientError, asyncio.TimeoutError):
            log.error(
                f"{self.__class__.__name__}: Connection error while making request to "
                f"the Plex Community API"
            )
            await asyncio.sleep(1)
            return await self._make_request(
                query=query, variables=variables, retry_count=retry_count + 1
            )
