// Pure helpers behind ProductProvider: no React, no DOM, so they can be tested with plain Node.
export type Language = 'vi' | 'en';
export type Theme = 'system' | 'light' | 'dark';
export type Accent = 'teal' | 'blue' | 'violet';
export type Preferences = { language: Language; theme: Theme; accent: Accent; textSize: 'standard' | 'large' };

/** The first language the browser lists decides; only Vietnamese and English are supported. */
export function detectLanguage(languages: readonly string[] | undefined): Language {
    const first = languages?.[0]?.toLowerCase() ?? '';
    return first === 'vi' || first.startsWith('vi-') ? 'vi' : 'en';
}

export function readPreferences(raw: string | null, languages: readonly string[] | undefined): Preferences {
    let value: Record<string, unknown> = {};
    try {
        const parsed = JSON.parse(raw ?? '{}');
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) value = parsed;
    } catch { /* unreadable storage: use the defaults below */ }
    const pick = <T extends string>(allowed: readonly T[], candidate: unknown, fallback: T): T => allowed.includes(candidate as T) ? candidate as T : fallback;
    return {
        language: pick(['vi', 'en'], value.language, detectLanguage(languages)),
        theme: pick(['system', 'light', 'dark'], value.theme, 'system'),
        accent: pick(['teal', 'blue', 'violet'], value.accent, 'teal'),
        textSize: value.textSize === 'large' ? 'large' : 'standard',
    };
}

/** Collects Vietnamese strings that have no translation. Recording is on only during an audit (tests, probes). */
export class MissingTranslations {
    private seen = new Set<string>();
    private recording: boolean;
    constructor(recording: boolean) { this.recording = recording; }
    note(text: string) {
        if (this.recording && /[A-Za-z]{2}/.test(text)) this.seen.add(text);
    }
    list() { return [...this.seen]; }
}
