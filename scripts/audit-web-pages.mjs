/**
 * Read-only visual and i18n audit of every web page against a running lab (the real one or the test lab).
 *   node scripts/audit-web-pages.mjs <base url> <fresh output directory> [--matrix vi:light:1440,vi:light:375,en:dark:1440] [--user admin] [--only events,artifacts] [--credentials <file>]
 * It only navigates (GET); it never clicks a button that changes data. For each language:theme:width it
 *   - opens the browser with that locale (so the default-language rule is exercised),
 *   - visits every route, takes a full-page screenshot, and records horizontal overflow, console errors
 *     and every Vietnamese string that had no translation (the product-ui audit hook).
 * The password is read from the credentials file (default ~/.config/heteroes-m2/credentials.json) and never printed.
 */
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const [base, output] = process.argv.slice(2);
if (!base || !output) throw Error('usage: audit-web-pages.mjs <base url> <fresh output directory> [options]');
const option = (name, fallback) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : fallback; };
const matrix = option('--matrix', 'vi:light:1440,vi:light:375,en:dark:1440').split(',').map(item => { const [language, theme, width] = item.split(':'); return { language, theme, width: Number(width) }; });
const user = option('--user', 'admin');
const only = option('--only', '')?.split(',').filter(Boolean) ?? [];
const wanted = name => !only.length || only.includes(name);
const credentialsFile = option('--credentials', path.join(os.homedir(), '.config/heteroes-m2/credentials.json'));
const password = JSON.parse(await fs.readFile(credentialsFile, 'utf8')).users?.[user];
if (!password) throw Error('No password for that user in the credentials file');
await fs.mkdir(output, { recursive: true });
try { await fs.access(path.join(output, 'audit.json')); throw Error('Evidence already exists'); } catch (error) { if (error.code !== 'ENOENT') throw error; }

const browser = await chromium.launch({ headless: true });
const report = [];
const missingAll = new Map();
try {
    for (const { language, theme, width } of matrix) {
        const context = await browser.newContext({ viewport: { width, height: 900 }, locale: language === 'vi' ? 'vi-VN' : 'en-US', colorScheme: theme });
        await context.addInitScript(([chosenTheme]) => {
            globalThis.__HETEROES_I18N_AUDIT__ = true;
            try { localStorage.setItem('heteroes.preferences', JSON.stringify({ theme: chosenTheme })); } catch { /* blocked storage */ }
        }, [theme]);
        const page = await context.newPage();
        const problems = [];
        page.on('pageerror', error => problems.push('pageerror: ' + error.message));
        // A signed-out visitor's session probe is answered 401 by design; anything else is a real problem.
        page.on('console', message => { if (message.type() === 'error' && !/status of 401/.test(message.text())) problems.push('console: ' + message.text().slice(0, 200)); });
        // Public pages first (signed out), then the signed-in application.
        const folder = path.join(output, `${language}-${theme}-${width}`);
        await fs.mkdir(folder, { recursive: true });
        const visit = async (name, url, ready = '#main-content, .auth-layout, .public-site') => {
            const before = problems.length;
            await page.goto(base + url, { waitUntil: 'domcontentloaded' });
            await page.locator(ready).first().waitFor({ timeout: 20000 }).catch(() => problems.push('not ready: ' + url));
            await page.waitForTimeout(1400);
            const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
            const missing = await page.evaluate(() => globalThis.__heteroesMissingI18n?.() ?? []);
            for (const text of missing) if (!missingAll.has(text)) missingAll.set(text, name);
            const height = await page.evaluate(() => document.documentElement.scrollHeight);
            await page.screenshot({ path: path.join(folder, name + '.png'), fullPage: true });
            report.push({ language, theme, width, page: name, url, overflow, height, newProblems: problems.slice(before) });
        };
        if (wanted('home')) await visit('home', '/');
        if (wanted('login')) await visit('login', '/login');
        if (wanted('register')) await visit('register', '/register');
        await page.goto(base + '/login');
        await page.locator('input[autocomplete="username"]').fill(user);
        await page.locator('input[autocomplete="current-password"]').fill(password);
        await page.locator('form button[type="submit"]').click();
        await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 30000 });
        const token = await page.evaluate(() => sessionStorage.getItem('heteroes.access-token'));
        const api = async route => page.evaluate(async ([path, bearer]) => { const reply = await fetch(path, { headers: { Authorization: 'Bearer ' + bearer, 'X-Workspace-Id': sessionStorage.getItem('heteroes.demo-workspace') ?? '' } }); return reply.ok ? reply.json() : null; }, [route, token]);
        const experiments = (await api('/api/v1/experiments')) ?? [];
        const best = [...experiments].filter(e => e.status === 'COMPLETED').sort((a, b) => (b.completedGenerations ?? 0) - (a.completedGenerations ?? 0))[0] ?? experiments[0];
        const generations = best ? (await api(`/api/v1/experiments/${best.experimentId}/generations`)) ?? [] : [];
        const candidates = generations[0] ? (await api(`/api/v1/generations/${generations[0].generationId}/candidates`)) ?? [] : [];
        const workers = (await api('/api/v1/workers')) ?? [];
        const routes = [['get-started', '/get-started'], ['dashboard', '/dashboard'], ['workspace', '/workspace'], ['workers', '/workers'], ['models', '/models'], ['experiments', '/experiments'], ['experiment-new', '/experiments/new'],
            ['artifacts', '/artifacts'], ['events', '/events'], ['operations', '/operations'], ['profile', '/profile']];
        if (best) routes.push(['experiment-detail', `/experiments/${best.experimentId}`]);
        if (generations[0]) routes.push(['generation-detail', `/experiments/${best.experimentId}/generations/${generations[0].generationId}`]);
        if (candidates[0]) routes.push(['candidate-detail', `/experiments/${best.experimentId}/generations/${generations[0].generationId}/candidates/${candidates[0].candidateId}`]);
        if (workers[0]) routes.push(['worker-detail', `/workers/${workers[0].workerId}`]);
        routes.push(['not-found', '/this-page-does-not-exist']);
        for (const [name, url] of routes) if (wanted(name)) await visit(name, url);
        await context.close();
    }
    const summary = {
        base, matrix, pages: report.length,
        overflowing: report.filter(r => r.overflow).map(r => `${r.language}:${r.theme}:${r.width} ${r.page}`),
        withProblems: report.filter(r => r.newProblems.length).map(r => ({ page: `${r.language}:${r.theme}:${r.width} ${r.page}`, problems: r.newProblems })),
        untranslated: [...missingAll].map(([text, page]) => ({ text, firstSeenOn: page })),
        tallest: [...report].sort((a, b) => b.height - a.height).slice(0, 8).map(r => `${r.language}:${r.theme}:${r.width} ${r.page} ${r.height}px`),
    };
    await fs.writeFile(path.join(output, 'audit.json'), JSON.stringify({ summary, report }, null, 1));
    console.log(JSON.stringify({ pages: summary.pages, overflowing: summary.overflowing.length, withProblems: summary.withProblems.length, untranslated: summary.untranslated.length }));
} finally { await browser.close(); }
