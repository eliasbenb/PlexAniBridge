from enum import Enum
from typing import Optional

from pydantic import BaseModel


class AniListBaseModel(BaseModel):
    @staticmethod
    def as_graphql() -> str:
        raise NotImplementedError


class AniListPageInfo(AniListBaseModel):
    total: Optional[int]
    perPage: Optional[int]
    currentPage: Optional[int]
    lastPage: Optional[int]
    hasNextPage: bool

    @staticmethod
    def as_graphql() -> str:
        return """
        pageInfo {
            total
            perPage
            currentPage
            lastPage
            hasNextPage
        }
        """


class AniListMediaStatus(Enum):
    FINISHED = "FINISHED"
    RELEASING = "RELEASING"
    NOT_YET_RELEASED = "NOT_YET_RELEASED"
    CANCELLED = "CANCELLED"
    HIATUS = "HIATUS"


class AniListMediaType(Enum):
    ANIME = "ANIME"
    MANGA = "MANGA"


class AniListMediaTitle(AniListBaseModel):
    romaji: Optional[str]
    english: Optional[str]
    native: Optional[str]

    @staticmethod
    def as_graphql() -> str:
        return (
            """
        title {
            romaji"""
            """
            english
            native
        }
        """
        )


class AniListFuzzyDate(AniListBaseModel):
    year: Optional[int]
    month: Optional[int]
    day: Optional[int]

    @staticmethod
    def as_graphql() -> str:
        return """
        year
        month
        day
        """

    def __eq__(self, other: "AniListFuzzyDate") -> bool:
        return (
            self.year == other.year
            and self.month == other.month
            and self.day == other.day
        )


class AniListMediaListStatus(Enum):
    _ignore_ = ["__priority"]

    CURRENT = "CURRENT"
    PLANNING = "PLANNING"
    COMPLETED = "COMPLETED"
    DROPPED = "DROPPED"
    PAUSED = "PAUSED"
    REPEATING = "REPEATING"

    __priority = {
        "REPEATING": 0,
        "COMPLETED": 1,
        "CURRENT": 2,
        "DROPPED": 3,
        "PAUSED": 4,
        "PLANNING": 5,
    }

    def __lt__(self, other: "AniListMediaListStatus") -> bool:
        return self.__priority[self.value] > self.__priority[other.value]

    def __le__(self, other: "AniListMediaListStatus") -> bool:
        return self.__priority[self.value] >= self.__priority[other.value]

    def __gt__(self, other: "AniListMediaListStatus") -> bool:
        return self.__priority[self.value] < self.__priority[other.value]

    def __ge__(self, other: "AniListMediaListStatus") -> bool:
        return self.__priority[self.value] <= self.__priority[other.value]


class AniListMediaList(AniListBaseModel):
    id: int
    mediaId: int
    status: AniListMediaListStatus
    score: Optional[float]
    progress: Optional[int]
    repeat: Optional[int]
    notes: Optional[str]
    startedAt: AniListFuzzyDate
    completedAt: AniListFuzzyDate

    @staticmethod
    def as_graphql() -> str:
        return f"""
        id
        mediaId
        status
        score
        progress
        repeat
        notes
        startedAt {{
            {AniListFuzzyDate.as_graphql()}
        }}
        completedAt {{
            {AniListFuzzyDate.as_graphql()}
        }}
        """


class AniListMedia(AniListBaseModel):
    id: int
    idMal: Optional[int]
    title: AniListMediaTitle
    type: AniListMediaType
    status: AniListMediaStatus
    startDate: AniListFuzzyDate
    endDate: AniListFuzzyDate
    seasonYear: Optional[int]
    episodes: Optional[int]
    mediaListEntry: Optional[AniListMediaList]

    @property
    def best_title(self) -> str:
        return self.title.english or self.title.romaji or self.title.native

    @staticmethod
    def as_graphql() -> str:
        return f"""
        id
        idMal
        {AniListMediaTitle.as_graphql()}
        type
        status
        startDate {{
            {AniListFuzzyDate.as_graphql()}
        }}
        endDate {{
            {AniListFuzzyDate.as_graphql()}
        }}
        seasonYear
        episodes
        mediaListEntry {{
            {AniListMediaList.as_graphql()}
        }}
        """


class AniListMediaEdge(AniListBaseModel):
    node: AniListMedia

    @staticmethod
    def as_graphql() -> str:
        return f"""
        node {{
            {AniListMedia.as_graphql()}
        }}
        """


class AniListMediaConnection(AniListBaseModel):
    nodes: Optional[list[AniListMedia]]
    pageInfo: Optional[AniListPageInfo]

    @staticmethod
    def as_graphql() -> str:
        return f"""
        nodes {{
            {AniListMedia.as_graphql()}
        }}
        {AniListPageInfo.as_graphql()}
        """


class AniListMediaWithRelations(AniListMedia):
    relations: AniListMediaConnection

    @staticmethod
    def as_graphql() -> str:
        return f"""
        {AniListMedia.as_graphql()}
        relations{{
            {AniListMediaConnection.as_graphql()}
        }}
        """
