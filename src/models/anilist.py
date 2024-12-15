from enum import Enum
from typing import Optional

from pydantic import BaseModel


class AnilistBaseModel(BaseModel):
    @staticmethod
    def as_graphql() -> str:
        raise NotImplementedError


class AnilistPageInfo(AnilistBaseModel):
    total: int
    perPage: int
    currentPage: int
    lastPage: int
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


class AnilistMediaStatus(Enum):
    FINISHED = "FINISHED"
    RELEASING = "RELEASING"
    NOT_YET_RELEASED = "NOT_YET_RELEASED"
    CANCELLED = "CANCELLED"
    HIATUS = "HIATUS"


class AnilistMediaType(Enum):
    ANIME = "ANIME"
    MANGA = "MANGA"


class AnilistMediaTitle(AnilistBaseModel):
    romaji: Optional[str]
    english: Optional[str]
    native: Optional[str]

    @staticmethod
    def as_graphql() -> str:
        return """
        title {
            romaji
            english
            native
        }
        """


class AnilistFuzzyDate(AnilistBaseModel):
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


class AnilistMediaListStatus(Enum):
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

    def __lt__(self, other: "AnilistMediaListStatus") -> bool:
        return self.__priority[self.value] > self.__priority[other.value]

    def __gt__(self, other: "AnilistMediaListStatus") -> bool:
        return self.__priority[self.value] < self.__priority[other.value]


class AnilistMediaList(AnilistBaseModel):
    id: int
    mediaId: int
    status: AnilistMediaListStatus
    score: Optional[float]
    progress: Optional[int]
    repeat: Optional[int]
    notes: Optional[str]
    startedAt: AnilistFuzzyDate
    completedAt: AnilistFuzzyDate

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
            {AnilistFuzzyDate.as_graphql()}
        }}
        completedAt {{
            {AnilistFuzzyDate.as_graphql()}
        }}
        """


class AnilistMedia(AnilistBaseModel):
    id: int
    idMal: Optional[int]
    title: AnilistMediaTitle
    type: AnilistMediaType
    status: AnilistMediaStatus
    startDate: AnilistFuzzyDate
    endDate: AnilistFuzzyDate
    seasonYear: Optional[int]
    episodes: Optional[int]
    mediaListEntry: Optional[AnilistMediaList]

    @property
    def best_title(self) -> str:
        return self.title.english or self.title.romaji or self.title.native

    @staticmethod
    def as_graphql() -> str:
        return f"""
        id
        idMal
        {AnilistMediaTitle.as_graphql()}
        type
        status
        startDate {{
            {AnilistFuzzyDate.as_graphql()}
        }}
        endDate {{
            {AnilistFuzzyDate.as_graphql()}
        }}
        seasonYear
        episodes
        mediaListEntry {{
            {AnilistMediaList.as_graphql()}
        }}
        """


class AnilistMediaEdge(AnilistBaseModel):
    node: AnilistMedia

    @staticmethod
    def as_graphql() -> str:
        return f"""
        node {{
            {AnilistMedia.as_graphql()}
        }}
        """


class AnilistMediaConnection(AnilistBaseModel):
    nodes: Optional[list[AnilistMedia]]
    pageInfo: Optional[AnilistPageInfo]

    @staticmethod
    def as_graphql() -> str:
        return f"""
        nodes {{
            {AnilistMedia.as_graphql()}
        }}
        {AnilistPageInfo.as_graphql()}
        """


class AnilistMediaWithRelations(AnilistMedia):
    relations: AnilistMediaConnection

    @staticmethod
    def as_graphql() -> str:
        return f"""
        {super().as_graphql()}
        relations{{
            {AnilistMediaConnection.as_graphql()}
        }}
        """
