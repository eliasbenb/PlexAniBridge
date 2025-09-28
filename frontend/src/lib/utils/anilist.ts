import { writable } from "svelte/store";

import type { MediaTitle } from "$lib/types/anilist";

export type TitleLanguage = "romaji" | "english" | "native" | "userPreferred";

const STORAGE_KEY = "anilist.lang";
const DEFAULT_LANG: TitleLanguage = "romaji";

function loadInitial(): TitleLanguage {
    try {
        const v = localStorage.getItem(STORAGE_KEY) as TitleLanguage | null;
        if (
            v === "romaji" ||
            v === "english" ||
            v === "native" ||
            v === "userPreferred"
        )
            return v;
    } catch {}
    return DEFAULT_LANG;
}

let currentLang: TitleLanguage = loadInitial();
export const anilistTitleLang = writable<TitleLanguage>(currentLang);

anilistTitleLang.subscribe((v) => {
    currentLang = v;
    try {
        localStorage.setItem(STORAGE_KEY, v);
    } catch {}
});

export function setAniListTitleLang(lang: TitleLanguage) {
    anilistTitleLang.set(lang);
}

export function preferredTitle(t?: MediaTitle | null): string | null {
    if (!t) return null;
    const baseOrder: TitleLanguage[] = ["romaji", "english", "native"];
    let order: TitleLanguage[];
    if (currentLang === "userPreferred") order = ["userPreferred", ...baseOrder];
    else order = [currentLang, ...baseOrder.filter((l) => l !== currentLang)];
    for (const key of order) {
        const val = (t as Record<string, string | null | undefined>)[key];
        if (val) return val;
    }
    return null;
}
