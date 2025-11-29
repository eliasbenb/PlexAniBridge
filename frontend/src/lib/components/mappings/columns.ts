import type { MappingOverrideMode } from "$lib/types/api";

export interface SeasonRow {
    season: string;
    value: string;
}

export type OverrideFieldType = "number" | "number_list" | "string_list" | "season";

export interface OverrideFieldDefinition {
    id: string;
    label: string;
    type: OverrideFieldType;
    placeholder?: string;
    hint?: string;
}

export type FieldStateValue = string | SeasonRow[];

export interface FieldState {
    mode: MappingOverrideMode;
    value: FieldStateValue;
}

export interface ColumnConfig {
    id: string;
    title: string;
    visible: boolean;
    width: number;
    minWidth: number;
    resizable: boolean;
}

export const defaultColumns: ColumnConfig[] = [
    {
        id: "title",
        title: "Title",
        visible: true,
        width: 256,
        minWidth: 200,
        resizable: true,
    },
    {
        id: "anilist",
        title: "AniList",
        visible: true,
        width: 80,
        minWidth: 60,
        resizable: true,
    },
    {
        id: "anidb",
        title: "AniDB",
        visible: true,
        width: 80,
        minWidth: 60,
        resizable: true,
    },
    {
        id: "imdb",
        title: "IMDB",
        visible: true,
        width: 100,
        minWidth: 80,
        resizable: true,
    },
    {
        id: "tmdb_movie",
        title: "TMDB (Movie)",
        visible: true,
        width: 120,
        minWidth: 100,
        resizable: true,
    },
    {
        id: "tmdb_show",
        title: "TMDB (Show)",
        visible: true,
        width: 120,
        minWidth: 100,
        resizable: true,
    },
    {
        id: "tvdb",
        title: "TVDB",
        visible: true,
        width: 80,
        minWidth: 60,
        resizable: true,
    },
    {
        id: "mal",
        title: "MAL",
        visible: true,
        width: 80,
        minWidth: 60,
        resizable: true,
    },
    {
        id: "tmdb_mappings",
        title: "TMDB Mappings",
        visible: true,
        width: 80,
        minWidth: 60,
        resizable: true,
    },
    {
        id: "tvdb_mappings",
        title: "TVDB Mappings",
        visible: true,
        width: 80,
        minWidth: 60,
        resizable: true,
    },
    {
        id: "source",
        title: "Source",
        visible: true,
        width: 80,
        minWidth: 60,
        resizable: true,
    },
    {
        id: "actions",
        title: "Actions",
        visible: true,
        width: 100,
        minWidth: 80,
        resizable: false,
    },
];

export const mappingSchema = {
    title: "AniBridge Mapping Override",
    type: "object",
    required: ["anilist_id"],
    additionalProperties: false,
    properties: {
        anilist_id: { type: ["integer", "null"], description: "The AniList ID" },
        anidb_id: { type: ["integer", "null"], description: "The AniDB ID" },
        imdb_id: {
            anyOf: [
                { type: "array", items: { type: "string", pattern: "^tt[0-9]{7,}$" } },
                { type: "null" },
            ],
            description: "Array of IMDB IDs in the format tt1234567 (or null)",
        },
        mal_id: {
            anyOf: [{ type: "array", items: { type: "integer" } }, { type: "null" }],
            description: "Array of MyAnimeList IDs (or null)",
        },
        tmdb_movie_id: {
            anyOf: [{ type: "array", items: { type: "integer" } }, { type: "null" }],
            description: "Array of TMDB movie IDs (or null)",
        },
        tmdb_show_id: { type: ["integer", "null"], description: "The TMDB Show ID" },
        tvdb_id: { type: ["integer", "null"], description: "The TVDB ID" },
        tmdb_mappings: {
            anyOf: [
                {
                    type: "object",
                    patternProperties: {
                        "^s[0-9]+$": {
                            type: "string",
                            description: "TMDB episode mappings pattern",
                            examples: ["e1-e12"],
                        },
                    },
                    additionalProperties: false,
                    description: "Season to episode mapping patterns",
                },
                { type: "null" },
            ],
        },
        tvdb_mappings: {
            anyOf: [
                {
                    type: "object",
                    patternProperties: {
                        "^s[0-9]+$": {
                            type: "string",
                            description: "TVDB episode mappings pattern",
                            examples: ["e1-e12"],
                        },
                    },
                    additionalProperties: false,
                    description: "Season to episode mapping patterns",
                },
                { type: "null" },
            ],
        },
    },
};

export const FIELD_DEFS: OverrideFieldDefinition[] = [
    { id: "anidb_id", label: "AniDB ID", type: "number", placeholder: "e.g. 12345" },
    {
        id: "imdb_id",
        label: "IMDb IDs",
        type: "string_list",
        placeholder: "tt12345, tt67890",
    },
    {
        id: "mal_id",
        label: "MyAnimeList IDs",
        type: "number_list",
        placeholder: "12345, 67890",
    },
    {
        id: "tmdb_movie_id",
        label: "TMDB Movie IDs",
        type: "number_list",
        placeholder: "12345, 67890",
    },
    { id: "tmdb_show_id", label: "TMDB Show ID", type: "number", placeholder: "12345" },
    { id: "tvdb_id", label: "TVDB ID", type: "number", placeholder: "12345" },
    {
        id: "tmdb_mappings",
        label: "TMDB Season Mappings",
        type: "season",
        hint: "Season key (e.g. s1) mapped to episode pattern",
    },
    {
        id: "tvdb_mappings",
        label: "TVDB Season Mappings",
        type: "season",
        hint: "Season key (e.g. s1) mapped to episode pattern",
    },
];

export type FieldId = (typeof FIELD_DEFS)[number]["id"];
export type FieldStateMap = Record<FieldId, FieldState>;
