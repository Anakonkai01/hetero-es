import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { translations } from './translations';
import { MissingTranslations, readPreferences, type Accent, type Language, type Preferences, type Theme } from './preferences';
export type { Accent, Language, Theme };
const STORAGE_KEY = 'heteroes.preferences';
const defaults: Preferences = readPreferences(null, []);
const Context = createContext<{
    preferences: Preferences;
    setPreferences: (value: Partial<Preferences>) => void;
    t: (value: string) => string;
}>({ preferences: defaults, setPreferences: () => { }, t: value => value });
const browserLanguages = () => typeof navigator === 'undefined' ? [] : navigator.languages?.length ? navigator.languages : [navigator.language];
declare global {
    // Set by tests and probes before the page loads to collect untranslated Vietnamese strings.
    var __HETEROES_I18N_AUDIT__: boolean | undefined;
    var __heteroesMissingI18n: (() => string[]) | undefined;
}
export function ProductProvider({ children }: {
    children: ReactNode;
}) {
    // What the person chose is stored; what the browser suggests is not, so a new browser language is followed until a choice is made.
    const [stored, setStored] = useState<string | null>(() => { try { return localStorage.getItem(STORAGE_KEY); } catch { return null; } });
    const preferences = useMemo(() => readPreferences(stored, browserLanguages()), [stored]);
    const missing = useMemo(() => new MissingTranslations(Boolean(globalThis.__HETEROES_I18N_AUDIT__)), []);
    useEffect(() => { globalThis.__heteroesMissingI18n = () => missing.list(); }, [missing]);
    useEffect(() => {
        const media = matchMedia('(prefers-color-scheme: dark)');
        const apply = () => { document.documentElement.dataset.theme = preferences.theme === 'system' ? (media.matches ? 'dark' : 'light') : preferences.theme; document.documentElement.dataset.accent = preferences.accent; document.documentElement.lang = preferences.language; document.documentElement.dataset.textSize = preferences.textSize; };
        apply();
        media.addEventListener('change', apply);
        return () => media.removeEventListener('change', apply);
    }, [preferences]);
    const t = (value: string) => {
        if (preferences.language !== 'vi')
            return value;
        const translated = translations[value];
        if (translated === undefined)
            missing.note(value);
        return translated ?? value;
    };
    const setPreferences = (value: Partial<Preferences>) => {
        let previous: Record<string, unknown> = {};
        try { previous = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') ?? {}; } catch { /* start from nothing */ }
        const next = JSON.stringify({ ...previous, ...value });
        try { localStorage.setItem(STORAGE_KEY, next); } catch { /* storage may be blocked: the choice then lasts for this visit only */ }
        setStored(next);
    };
    return <Context.Provider value={{ preferences, setPreferences, t }}>{children}</Context.Provider>;
}
export function useProduct() { return useContext(Context); }
export function PreferencesControl() {
    const { preferences, setPreferences, t } = useProduct();
    return <details className="preference-menu"><summary aria-label={t('Appearance and language')}><span aria-hidden="true">◐</span> {t('Appearance and language')}</summary><div className="preferences" aria-label={t('Appearance and language')}>
    <label><span>{t('Language')}</span><select aria-label={t('Language')} value={preferences.language} onChange={event => setPreferences({ language: event.target.value as Language })}><option value="vi">Tiếng Việt</option><option value="en">English</option></select></label>
    <label><span>{t('Theme')}</span><select aria-label={t('Theme')} value={preferences.theme} onChange={event => setPreferences({ theme: event.target.value as Theme })}><option value="system">{t('System')}</option><option value="light">{t('Light')}</option><option value="dark">{t('Dark')}</option></select></label>
    <label><span>{t('Accent')}</span><select aria-label={t('Accent')} value={preferences.accent} onChange={event => setPreferences({ accent: event.target.value as Accent })}><option value="teal">{t('Teal')}</option><option value="blue">{t('Blue')}</option><option value="violet">{t('Violet')}</option></select></label>
    <label><span>{t('Text size')}</span><select aria-label={t('Text size')} value={preferences.textSize} onChange={event => setPreferences({ textSize: event.target.value as Preferences['textSize'] })}><option value="standard">{t('Standard')}</option><option value="large">{t('Large')}</option></select></label>
  </div></details>;
}
export function Status({ value }: {
    value: string;
}) { const { t } = useProduct(); return <span className={`product-status status-${value.toLowerCase().replace(/[^a-z0-9_-]/g,'-')}`}>{t(value)}</span>; }
export function StepHeader({ steps, current }: {
    steps: string[];
    current: number;
}) { const { t } = useProduct(); return <ol className="product-steps" aria-label={t('Setup progress')}>{steps.map((step, index) => <li key={step} aria-current={index === current ? 'step' : undefined} className={index === current ? 'current' : index < current ? 'done' : ''}><span>{index < current ? '✓' : index + 1}</span>{t(step)}</li>)}</ol>; }
export function Alert({ children, tone = 'info' }: {
    children: ReactNode;
    tone?: 'info' | 'error' | 'warning';
}) { return <div className={`product-alert ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>{children}</div>; }

export function ProductMark() {
    return <svg viewBox="0 0 32 32" width="32" height="32" fill="none" aria-hidden="true"><rect width="32" height="32" rx="9" fill="currentColor"/><path d="M9 22v-6m7 6V10m7 12V7" stroke="var(--on-acc)" strokeWidth="3" strokeLinecap="round"/></svg>;
}

export function CopyValue({value,label='Copy'}:{value:string;label?:string}) {
    const {t}=useProduct();const [result,setResult]=useState('');
    return <div className="copy-value"><code>{value}</code><button type="button" className="secondary" onClick={()=>void navigator.clipboard.writeText(value).then(()=>setResult('Copied')).catch(()=>setResult('Select and copy manually'))}>{t(result||label)}</button><span className="sr-only" role="status">{t(result)}</span></div>;
}
export {ResourceTelemetry,readableBytes,type ResourceObservation,type ResourceHistoryPoint} from './telemetry';

export function useObservationTime(){
 const [now,setNow]=useState(()=>Date.now()/1000);
 useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()/1000),5000);return()=>clearInterval(timer);},[]);
 return now;
}

export {fleetResources} from './fleet';
