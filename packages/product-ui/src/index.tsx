import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { translations } from './translations';
export type Language = 'vi' | 'en';
export type Theme = 'system' | 'light' | 'dark';
export type Accent = 'teal' | 'blue' | 'violet';
type Preferences = {
    language: Language;
    theme: Theme;
    accent: Accent;
};
const defaults: Preferences = { language: 'vi', theme: 'system', accent: 'teal' };
const Context = createContext<{
    preferences: Preferences;
    setPreferences: (value: Partial<Preferences>) => void;
    t: (value: string) => string;
}>({ preferences: defaults, setPreferences: () => { }, t: value => value });
export function ProductProvider({ children }: {
    children: ReactNode;
}) {
    const [preferences, set] = useState<Preferences>(() => {
        try {
            const value = JSON.parse(localStorage.getItem('heteroes.preferences') ?? '{}');
            return { language: ['vi', 'en'].includes(value.language) ? value.language : 'vi', theme: ['system', 'light', 'dark'].includes(value.theme) ? value.theme : 'system', accent: ['teal', 'blue', 'violet'].includes(value.accent) ? value.accent : 'teal' };
        }
        catch {
            return defaults;
        }
    });
    useEffect(() => {
        const media = matchMedia('(prefers-color-scheme: dark)');
        const apply = () => { document.documentElement.dataset.theme = preferences.theme === 'system' ? (media.matches ? 'dark' : 'light') : preferences.theme; document.documentElement.dataset.accent = preferences.accent; document.documentElement.lang = preferences.language; };
        apply();
        media.addEventListener('change', apply);
        localStorage.setItem('heteroes.preferences', JSON.stringify(preferences));
        return () => media.removeEventListener('change', apply);
    }, [preferences]);
    const t = (value: string) => preferences.language === 'vi' ? (translations[value] ?? value) : value;
    return <Context.Provider value={{ preferences, setPreferences: value => set(old => ({ ...old, ...value })), t }}>{children}</Context.Provider>;
}
export function useProduct() { return useContext(Context); }
export function PreferencesControl() {
    const { preferences, setPreferences, t } = useProduct();
    return <div className="preferences" aria-label={t('Appearance and language')}>
    <label><span>{t('Language')}</span><select aria-label={t('Language')} value={preferences.language} onChange={event => setPreferences({ language: event.target.value as Language })}><option value="vi">Tiếng Việt</option><option value="en">English</option></select></label>
    <label><span>{t('Theme')}</span><select aria-label={t('Theme')} value={preferences.theme} onChange={event => setPreferences({ theme: event.target.value as Theme })}><option value="system">{t('System')}</option><option value="light">{t('Light')}</option><option value="dark">{t('Dark')}</option></select></label>
    <label><span>{t('Accent')}</span><select aria-label={t('Accent')} value={preferences.accent} onChange={event => setPreferences({ accent: event.target.value as Accent })}><option value="teal">{t('Teal')}</option><option value="blue">{t('Blue')}</option><option value="violet">{t('Violet')}</option></select></label>
  </div>;
}
export function Status({ value }: {
    value: string;
}) { const { t } = useProduct(); return <span className={`product-status status-${value.toLowerCase()}`}>{t(value)}</span>; }
export function StepHeader({ steps, current }: {
    steps: string[];
    current: number;
}) { const { t } = useProduct(); return <ol className="product-steps" aria-label={t('Setup progress')}>{steps.map((step, index) => <li key={step} aria-current={index === current ? 'step' : undefined} className={index === current ? 'current' : index < current ? 'done' : ''}><span>{index < current ? '✓' : index + 1}</span>{t(step)}</li>)}</ol>; }
export function Alert({ children, tone = 'info' }: {
    children: ReactNode;
    tone?: 'info' | 'error' | 'warning';
}) { return <div className={`product-alert ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>{children}</div>; }
