from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from functools import total_ordering
from typing import Annotated, ClassVar, Optional, Union, get_args, get_origin

from pydantic import AfterValidator, AliasGenerator, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

UTCDateTime = Annotated[
    datetime, AfterValidator(lambda dt: dt.astimezone(timezone.utc))
]


class AniListBaseEnum(StrEnum):
    pass


class MediaType(AniListBaseEnum):
    ANIME = "ANIME"
    MANGA = "MANGA"


class MediaFormat(AniListBaseEnum):
    TV = "TV"
    TV_SHORT = "TV_SHORT"
    MOVIE = "MOVIE"
    SPECIAL = "SPECIAL"
    OVA = "OVA"
    ONA = "ONA"
    MUSIC = "MUSIC"
    MANGA = "MANGA"
    NOVEL = "NOVEL"
    ONE_SHOT = "ONE_SHOT"


class MediaStatus(AniListBaseEnum):
    FINISHED = "FINISHED"
    RELEASING = "RELEASING"
    NOT_YET_RELEASED = "NOT_YET_RELEASED"
    CANCELLED = "CANCELLED"
    HIATUS = "HIATUS"


class MediaSeason(AniListBaseEnum):
    WINTER = "WINTER"
    SPRING = "SPRING"
    SUMMER = "SUMMER"
    FALL = "FALL"


class MediaSort(AniListBaseEnum):
    ID = "ID"
    ID_DESC = "ID_DESC"
    TITLE_ROMAJI = "TITLE_ROMAJI"
    TITLE_ROMAJI_DESC = "TITLE_ROMAJI_DESC"
    TITLE_ENGLISH = "TITLE_ENGLISH"
    TITLE_ENGLISH_DESC = "TITLE_ENGLISH_DESC"
    TITLE_NATIVE = "TITLE_NATIVE"
    TITLE_NATIVE_DESC = "TITLE_NATIVE_DESC"
    TYPE = "TYPE"
    TYPE_DESC = "TYPE_DESC"
    FORMAT = "FORMAT"
    FORMAT_DESC = "FORMAT_DESC"
    START_DATE = "START_DATE"
    START_DATE_DESC = "START_DATE_DESC"
    END_DATE = "END_DATE"
    END_DATE_DESC = "END_DATE_DESC"
    SCORE = "SCORE"
    SCORE_DESC = "SCORE_DESC"
    POPULARITY = "POPULARITY"
    POPULARITY_DESC = "POPULARITY_DESC"
    TRENDING = "TRENDING"
    TRENDING_DESC = "TRENDING_DESC"
    EPISODES = "EPISODES"
    EPISODES_DESC = "EPISODES_DESC"
    DURATION = "DURATION"
    DURATION_DESC = "DURATION_DESC"
    STATUS = "STATUS"
    STATUS_DESC = "STATUS_DESC"
    CHAPTERS = "CHAPTERS"
    CHAPTERS_DESC = "CHAPTERS_DESC"
    VOLUMES = "VOLUMES"
    VOLUMES_DESC = "VOLUMES_DESC"
    UPDATED_AT = "UPDATED_AT"
    UPDATED_AT_DESC = "UPDATED_AT_DESC"
    SEARCH_MATCH = "SEARCH_MATCH"
    FAVOURITES = "FAVOURITES"
    FAVOURITES_DESC = "FAVOURITES_DESC"


class MediaListStatus(AniListBaseEnum):
    _ignore_ = ["__priority"]

    CURRENT = "CURRENT"
    PLANNING = "PLANNING"
    COMPLETED = "COMPLETED"
    DROPPED = "DROPPED"
    PAUSED = "PAUSED"
    REPEATING = "REPEATING"

    __priority = {
        "PLANNING": 1,
        "CURRENT": 2,
        "PAUSED": 2,
        "DROPPED": 2,
        "COMPLETED": 3,
        "REPEATING": 3,
    }

    def __eq__(self, other) -> bool:
        if self.__class__ is not other.__class__:
            return NotImplemented
        return self.value == other.value

    def __ne__(self, other) -> bool:
        if self.__class__ is not other.__class__:
            return NotImplemented
        return self.value != other.value

    def __lt__(self, other) -> bool:
        if self.__class__ is not other.__class__:
            return NotImplemented
        return (
            self.value != other.value
            and self.__priority[self.value] <= self.__priority[other.value]
        )

    def __le__(self, other) -> bool:
        if self.__class__ is not other.__class__:
            return NotImplemented
        return self.__priority[self.value] <= self.__priority[other.value]

    def __gt__(self, other) -> bool:
        if self.__class__ is not other.__class__:
            return NotImplemented
        return (
            self.value != other.value
            and self.__priority[self.value] >= self.__priority[other.value]
        )

    def __ge__(self, other) -> bool:
        if self.__class__ is not other.__class__:
            return NotImplemented
        return self.__priority[self.value] >= self.__priority[other.value]


class AniListBaseModel(BaseModel):
    """Base, abstract class for all AniList models to represent GraphQL objects"""

    _processed_models: ClassVar[set] = set()

    def model_dump(self, **kwargs) -> dict:
        """Convert the model to a dictionary, converting all keys to camelCase

        Because AniList uses camelCase for its GraphQL API, we need to convert all the keys to camelCase.

        Returns:
            dict: Dictionary representation of the model
        """
        return super().model_dump(by_alias=True, **kwargs)

    def model_dump_json(self, **kwargs) -> str:
        """Serialize the model to JSON, converting all keys to camelCase

        Because AniList uses camelCase for its GraphQL API, we need to convert all the keys to camelCase.

        Returns:
            str: JSON serialized string of the model
        """
        return super().model_dump_json(by_alias=True, **kwargs)

    def clear(self) -> None:
        """Clear all the fields of the model"""
        for field, field_info in self.model_fields.items():
            if field_info.default_factory:
                default_value = field_info.default_factory()
            else:
                default_value = field_info.default
            setattr(self, field, default_value)
        self.model_fields_set.clear()

    @classmethod
    def model_dump_graphql(cls, indent_level: int = 0) -> str:
        """Generate GraphQL query fields with proper indentation

        This is a class method that converts all the avaiilable fields into a GraphQL query with support for nested fields.
        This allows us to dynamically generate GraphQL queries without having to manually write them for each model.

        Args:
            indent_level (int, optional): How many levels to indent. Defaults to 0.

        Returns:
            str: The GraphQL query fields with proper indentation
        """
        if cls.__name__ in cls._processed_models:
            return ""

        cls._processed_models.add(cls.__name__)
        fields = cls.model_fields
        graphql_fields = []
        indent = "    " * indent_level

        for field_name, field in fields.items():
            field_type = (
                get_args(field.annotation)[0]
                if get_origin(field.annotation)
                else field.annotation
            )

            camel_field_name = to_camel(field_name)

            if isinstance(field_type, type) and issubclass(
                field_type, AniListBaseModel
            ):
                nested_fields = field_type.model_dump_graphql(indent_level + 1)
                if nested_fields:
                    graphql_fields.append(
                        f"{indent}{camel_field_name} {{\n{nested_fields}\n{indent}}}"
                    )
            else:
                graphql_fields.append(f"{indent}{camel_field_name}")

        cls._processed_models.remove(cls.__name__)
        return "\n".join(graphql_fields)

    model_config = ConfigDict(
        alias_generator=AliasGenerator(to_camel), populate_by_name=True
    )


class User(AniListBaseModel):
    id: int
    name: str


class PageInfo(AniListBaseModel):
    total: Optional[int] = None
    per_page: Optional[int] = None
    current_page: Optional[int] = None
    last_page: Optional[int] = None
    has_next_page: Optional[bool] = None


class MediaTitle(AniListBaseModel):
    romaji: Optional[str] = None
    english: Optional[str] = None
    native: Optional[str] = None

    def titles(self) -> list[str]:
        """Return a list of all the available titles

        Returns:
            list[str]: All the available titles
        """
        return [getattr(self, t) for t in self.model_fields if t]

    def __str__(self) -> str:
        """Return the first available title or an empty string

        Returns:
            str: A title or an empty string
        """
        return self.english or self.romaji or self.native or ""


@total_ordering
class FuzzyDate(AniListBaseModel):
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None

    @staticmethod
    def from_date(d: Union[date, datetime]) -> "FuzzyDate":
        """Create a FuzzyDate from a date or datetime object

        Args:
            d (Union[date, datetime]): A date or datetime object

        Returns:
            FuzzyDate: An equivalent FuzzyDate object
        """
        return FuzzyDate(year=d.year, month=d.month, day=d.day)

    def to_datetime(self) -> Optional[datetime]:
        """Convert the FuzzyDate to a datetime object

        Returns:
            Optional[datetime]: A datetime object or None if the FuzzyDate is incomplete
        """
        if not self.year:
            return None
        return datetime(year=self.year, month=self.month or 1, day=self.day or 1)

    def __eq__(self, other) -> bool:
        if not isinstance(other, FuzzyDate):
            return False
        return (
            self.year == other.year
            and self.month == other.month
            and self.day == other.day
        )

    def __lt__(self, other: Optional["FuzzyDate"]) -> bool:
        if other is None:
            return False
        return ((self.year or 0), (self.month or 0), (self.day or 0)) < (
            (other.year or 0),
            (other.month or 0),
            (other.day or 0),
        )

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return (
            f"{self.year or '????'}-"
            f"{str(self.month).zfill(2) if self.month else '??'}-"
            f"{str(self.day).zfill(2) if self.day else '??'}"
        )


class MediaList(AniListBaseModel):
    id: int
    user_id: int
    media_id: int
    status: Optional[MediaListStatus] = None
    score: Optional[float] = None
    progress: Optional[int] = None
    repeat: Optional[int] = None
    notes: Optional[str] = None
    started_at: Optional[FuzzyDate] = None
    completed_at: Optional[FuzzyDate] = None
    created_at: Optional[UTCDateTime] = None
    updated_at: Optional[UTCDateTime] = None

    def unset_fields(self, fields: list[str]) -> None:
        for field, field_info in self.model_fields.items():
            if field in fields:
                setattr(self, field, field_info.default)

    def __str__(self) -> str:
        notes_truncated = None
        if self.notes:
            notes_truncated = self.notes[:50].replace("\n", "  ") + "..."

        return (
            f"(status={self.status}, score={self.score}, progress={self.progress}, "
            f"repeat={self.repeat}, notes={notes_truncated}, started_at={self.started_at}, "
            f"completed_at={self.completed_at})"
        )


class MediaListGroup(AniListBaseModel):
    entries: list[MediaList] = []
    name: Optional[str] = None
    is_custom_list: Optional[bool] = None
    is_split_completed_list: Optional[bool] = None
    status: Optional[MediaListStatus] = None


class MediaListCollection(AniListBaseModel):
    user: Optional[User] = None
    lists: list[MediaListGroup] = []
    has_next_chunk: Optional[bool] = None


class AiringSchedule(AniListBaseModel):
    id: int
    airing_at: UTCDateTime
    time_until_airing: timedelta
    episode: int
    media_id: int


class Media(AniListBaseModel):
    id: int
    id_mal: Optional[int] = None
    type: Optional[MediaType] = None
    format: Optional[MediaFormat] = None
    status: Optional[MediaStatus] = None
    season: Optional[MediaSeason] = None
    season_year: Optional[int] = None
    episodes: Optional[int] = None
    duration: Optional[int] = None
    synonyms: Optional[list[str]] = None
    is_locked: Optional[bool] = None
    title: Optional[MediaTitle] = None
    start_date: Optional[FuzzyDate] = None
    end_date: Optional[FuzzyDate] = None
    next_airing_episode: Optional[AiringSchedule] = None
    media_list_entry: Optional[MediaList] = None


class MediaEdge(AniListBaseModel):
    node: Media


class MediaConnection(AniListBaseModel):
    nodes: list[Media]
    pageInfo: PageInfo = PageInfo()


class MediaWithRelations(Media):
    relations: MediaConnection
