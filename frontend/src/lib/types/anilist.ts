export type MediaType = "ANIME" | "MANGA";

export type MediaFormat =
    | "TV"
    | "TV_SHORT"
    | "MOVIE"
    | "SPECIAL"
    | "OVA"
    | "ONA"
    | "MUSIC"
    | "MANGA"
    | "NOVEL"
    | "ONE_SHOT";

export type MediaStatus =
    | "FINISHED"
    | "RELEASING"
    | "NOT_YET_RELEASED"
    | "CANCELLED"
    | "HIATUS";

export interface MediaTitle {
    romaji?: string | null;
    english?: string | null;
    native?: string | null;
    userPreferred?: string | null;
}

export interface MediaCoverImage {
    extraLarge?: string | null;
    large?: string | null;
    medium?: string | null;
    color?: string | null;
}

export interface MediaWithoutList {
    id: number;
    type?: MediaType | null;
    format?: MediaFormat | null;
    status?: MediaStatus | null;
    episodes?: number | null;
    duration?: number | null;
    coverImage?: MediaCoverImage | null;
    title?: MediaTitle | null;
}

export type Media = Pick<
    MediaWithoutList,
    "id" | "format" | "status" | "episodes" | "coverImage" | "title"
>;
