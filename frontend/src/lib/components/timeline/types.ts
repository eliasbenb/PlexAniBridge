import type { Circle } from "@lucide/svelte";

import type { HistoryItem } from "$lib/types/api";

export type DiffStatus = "added" | "removed" | "changed" | "unchanged";

export interface DiffEntry {
    path: string;
    before: unknown;
    after: unknown;
    status: DiffStatus;
}

export interface ItemDiffUi {
    tab: "changes" | "compare";
    filter: string;
    showUnchanged: boolean;
}

export interface OutcomeMeta {
    label: string;
    color: string;
    icon: typeof Circle;
    order: number;
}

export interface TimelineItemContext {
    item: HistoryItem;
    meta: OutcomeMeta;
}
