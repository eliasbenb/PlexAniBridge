import type {
    Media as AniListMedia,
    MediaWithoutList as AniListMediaWithoutList,
} from "$lib/types/anilist";

// --- Generic ---
export type ApiResult<T> = Promise<T>;

export interface OkResponse {
    ok: boolean;
}

// --- Mappings API ---
export interface Mapping {
    anilist_id: number;
    anidb_id?: number | null;
    imdb_id?: string[] | null;
    mal_id?: number[] | null;
    tmdb_movie_id?: number[] | null;
    tmdb_show_id?: number[] | null;
    tvdb_id?: number | null;
    tmdb_mappings?: Record<string, string> | null;
    tvdb_mappings?: Record<string, string> | null;
    anilist?: AniListMedia | null;
    custom?: boolean;
    sources?: string[];
}

export interface ListMappingsResponse {
    items: Mapping[];
    total: number;
    page: number;
    per_page: number;
    pages: number;
    with_anilist: boolean;
}

export type DeleteMappingResponse = OkResponse;

export type FieldType = "int" | "string" | "enum";
export type FieldOperator = "=" | ">" | ">=" | "<" | "<=" | "*" | "?" | "range";

export interface FieldCapability {
    key: string;
    aliases: string[];
    type: FieldType;
    operators: FieldOperator[];
    values?: string[] | null;
    desc?: string | null;
}

export interface QueryCapabilitiesResponse {
    fields: FieldCapability[];
}

// --- Logs API ---
export interface LogFile {
    name: string;
    size: number;
    mtime: number;
    current: boolean;
}

export interface LogEntry {
    timestamp: string | null;
    level: string;
    message: string;
}

// --- Status / System API ---
export interface ProfileConfig {
    plex_user?: string | null;
    anilist_user?: string | null;
    sync_interval?: number | null;
    sync_modes?: string[];
    full_scan?: boolean | null;
    destructive_sync?: boolean | null;
}

export interface CurrentSync {
    state?: string;
    started_at?: string;
    section_index?: number;
    section_count?: number;
    section_title?: string | null;
    stage?: string;
    section_items_total?: number;
    section_items_processed?: number;
}

export interface ProfileRuntimeStatus {
    running: boolean;
    last_synced?: string | null;
    current_sync?: CurrentSync | null;
}

export interface ProfileStatus {
    config: ProfileConfig;
    status: ProfileRuntimeStatus;
}

export interface StatusResponse {
    profiles: Record<string, ProfileStatus>;
}

export interface SettingsProfile {
    name: string;
    settings: Record<string, unknown>;
}

export interface SettingsResponse {
    global_config: Record<string, unknown>;
    profiles: SettingsProfile[];
}

export interface AboutInfo {
    version: string;
    git_hash: string;
    python: string;
    platform: string;
    utc_now: string;
    started_at?: string | null;
    uptime_seconds?: number | null;
    uptime?: string | null;
}

export interface AboutResponse {
    info: AboutInfo;
    status: Record<string, ProfileStatus>;
}

export interface MetaResponse {
    version: string;
    git_hash: string;
}

// --- History API ---
export interface HistoryItem {
    id: number;
    profile_name: string;
    plex_guid?: string | null;
    plex_rating_key?: string;
    plex_child_rating_key?: string | null;
    plex_type?: string;
    anilist_id?: number | null;
    outcome: string;
    before_state?: Record<string, unknown> | null;
    after_state?: Record<string, unknown> | null;
    error_message?: string | null;
    timestamp: string;
    anilist?: AniListMediaWithoutList | null;
    plex?: {
        guid?: string;
        title?: string;
        type?: string | null;
        art?: string | null;
        thumb?: string | null;
    } | null;
}

export interface GetHistoryResponse {
    items: HistoryItem[];
    page: number;
    per_page: number;
    total: number;
    pages: number;
    stats: Record<string, number>;
}

export interface UndoResponse {
    item: HistoryItem;
}

// --- Backups API ---
export interface BackupMeta {
    filename: string;
    created_at: string;
    size_bytes: number;
    entries?: number | null;
    user?: string | null;
    age_seconds: number;
}

export interface ListBackupsResponse {
    backups: BackupMeta[];
}

export interface RawBackup {
    [key: string]: unknown;
}

export interface RestoreSummary {
    ok: boolean;
    filename: string;
    total_entries: number;
    processed: number;
    restored: number;
    skipped: number;
    errors: Record<string, unknown>[];
    elapsed_seconds: number;
}
