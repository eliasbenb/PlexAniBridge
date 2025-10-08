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
