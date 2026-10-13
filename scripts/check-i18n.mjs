#!/usr/bin/env node
/**
 * Static i18n check for the web app, the two desktop apps and the shared UI package.
 *   node scripts/check-i18n.mjs [--list]
 * Fails (exit 1) when
 *   - a string passed to t('…') has no Vietnamese translation, or
 *   - a person-visible English string is written outside t(): JSX text, or a string-literal
 *     placeholder / title / aria-label / alt / label attribute.
 * Strings that are the same in both languages (product and model names, units) are listed in ALLOWED.
 * Strings chosen at run time (t(variable)) cannot be seen here; the browser probes cover them through
 * `globalThis.__HETEROES_I18N_AUDIT__` (see packages/product-ui/src/preferences.ts).
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { translations } from '../packages/product-ui/src/translations.ts';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sources = ['frontend/src', 'desktop/worker/src', 'desktop/server/src', 'packages/product-ui/src'];
const ATTRIBUTES = new Set(['placeholder', 'title', 'aria-label', 'alt', 'aria-description']);
// Written the same in Vietnamese and English.
// Brand eyebrows, option values that are identifiers, and sample data shown only in the demo build.
const ALLOWED_PATTERNS = [/^HETEROES\b/, /^HeteroES( Lab Server| Worker)?$/];
const ALLOWED = new Set(['constant', 'cosine', 'hf_generate', 'hf_compact', 'GSM8K · ####', 'admin, an, binh · demo-local', 'Mbps', 'GMT+7', 'name@example.com', 'organization/model', 'windows', 'linux-appimage', 'Qwen2.5 0.5B Instruct', 'SmolLM2 135M Instruct', 'HeteroES', 'Hetero', 'ES', 'GPU', 'GPUs', 'CPU', 'VRAM', 'RAM', 'Worker', 'Lab Server', 'Tailscale', 'WireGuard', 'Windows', 'Linux', 'AppImage', 'Telegram', 'SSE', 'CSV', 'PNG', 'PDF', 'JSON', 'UUID', 'ID', 'Qwen', 'arith16', 'GiB', 'MB', 'GB', 'MiB', 'W', 'Wh', 'MHz', 'Tiếng Việt', 'English']);

const files = [];
(function walk(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
        const full = path.join(directory, entry.name);
        if (entry.isDirectory()) { if (!['node_modules', 'dist'].includes(entry.name)) walk(full); }
        else if (entry.name.endsWith('.tsx')) files.push(full);
    }
})(root);
const inScope = file => sources.some(source => path.relative(root, file).startsWith(source + path.sep));

const needsTranslation = text => {
    const clean = text.replace(/[·|/\-–—:()]+$/, '').trim();
    return /[A-Za-z]{2}/.test(clean) && !ALLOWED.has(clean) && !ALLOWED_PATTERNS.some(pattern => pattern.test(clean));
};
const used = new Map();          // key -> first place
const bare = [];                 // [place, text]
let dynamic = 0;

for (const file of files.filter(inScope)) {
    const source = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const where = node => `${path.relative(root, file)}:${source.getLineAndCharacterOfPosition(node.getStart()).line + 1}`;
    // Strings a t(...) argument can evaluate to: not the operands of a comparison.
    const results = node => {
        if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return [node.text];
        if (ts.isParenthesizedExpression(node) || ts.isAsExpression(node) || ts.isNonNullExpression(node)) return results(node.expression);
        if (ts.isConditionalExpression(node)) return [...results(node.whenTrue), ...results(node.whenFalse)];
        if (ts.isBinaryExpression(node) && [ts.SyntaxKind.BarBarToken, ts.SyntaxKind.QuestionQuestionToken].includes(node.operatorToken.kind)) return [...results(node.left), ...results(node.right)];
        if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken) return results(node.right);
        return [];
    };
    (function visit(node) {
        if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 't' && node.arguments.length) {
            const keys = results(node.arguments[0]);
            if (!keys.length) dynamic++;
            for (const key of keys) if (!used.has(key)) used.set(key, where(node));
        } else if (ts.isJsxText(node)) {
            const text = node.text.replace(/\s+/g, ' ').trim();
            if (needsTranslation(text)) bare.push([where(node), text]);
        } else if (ts.isJsxAttribute(node) && ATTRIBUTES.has(node.name.text) && node.initializer && ts.isStringLiteral(node.initializer) && /^[a-z]/.test(node.parent.parent.tagName.getText())) {
            if (needsTranslation(node.initializer.text)) bare.push([where(node), `${node.name.text}="${node.initializer.text}"`]);
        } else if (ts.isJsxExpression(node) && node.expression && ts.isStringLiteral(node.expression) && ts.isJsxElement(node.parent)) {
            if (needsTranslation(node.expression.text)) bare.push([where(node), `{'${node.expression.text}'}`]);
        }
        ts.forEachChild(node, visit);
    })(source);
}

const missing = [...used].filter(([key]) => needsTranslation(key) && translations[key] === undefined);
const list = process.argv.includes('--list');
console.log(`t() keys: ${used.size}; computed (not checked here): ${dynamic}; missing Vietnamese: ${missing.length}; untranslated text outside t(): ${bare.length}`);
for (const [key, place] of missing.slice(0, list ? Infinity : 15)) console.log(`  MISSING ${place}  ${JSON.stringify(key)}`);
for (const [place, text] of bare.slice(0, list ? Infinity : 15)) console.log(`  BARE    ${place}  ${JSON.stringify(text)}`);
if (!list && (missing.length > 15 || bare.length > 15)) console.log('  … run with --list for everything');
process.exit(missing.length || bare.length ? 1 : 0);
