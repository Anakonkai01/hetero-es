import { test } from 'node:test';
import assert from 'node:assert/strict';
import { detectLanguage, readPreferences, MissingTranslations } from '../src/preferences.ts';

test('the language follows the browser unless the person chose one', () => {
    assert.equal(detectLanguage(['vi-VN', 'en-US']), 'vi');
    assert.equal(detectLanguage(['VI']), 'vi');
    assert.equal(detectLanguage(['en-US', 'vi']), 'en', 'the first preference decides');
    assert.equal(detectLanguage(['fr-FR']), 'en');
    assert.equal(detectLanguage([]), 'en');
    assert.equal(detectLanguage(undefined), 'en');
});

test('stored preferences win; anything unusable falls back to the browser language and safe defaults', () => {
    assert.deepEqual(readPreferences(null, ['vi-VN']), { language: 'vi', theme: 'system', accent: 'teal', textSize: 'standard' });
    assert.deepEqual(readPreferences(null, ['en-GB']), { language: 'en', theme: 'system', accent: 'teal', textSize: 'standard' });
    assert.equal(readPreferences(JSON.stringify({ language: 'en' }), ['vi-VN']).language, 'en');
    assert.equal(readPreferences(JSON.stringify({ language: 'vi' }), ['en-US']).language, 'vi');
    assert.equal(readPreferences(JSON.stringify({ theme: 'dark', accent: 'violet', textSize: 'large' }), ['vi']).theme, 'dark');
    assert.equal(readPreferences(JSON.stringify({ language: 'klingon', theme: 'neon', accent: 'red', textSize: 'huge' }), ['vi']).language, 'vi');
    assert.equal(readPreferences('{broken', ['vi']).language, 'vi');
    assert.equal(readPreferences('null', ['en']).language, 'en');
    assert.equal(readPreferences('[1]', ['en']).theme, 'system');
});

test('a missing Vietnamese string is reported once, and only while an audit is running', () => {
    const quiet = new MissingTranslations(false);
    quiet.note('Hello');
    assert.deepEqual(quiet.list(), []);
    const audit = new MissingTranslations(true);
    audit.note('Hello'); audit.note('Hello'); audit.note('World');
    assert.deepEqual(audit.list(), ['Hello', 'World']);
    audit.note('   ');
    audit.note('1234');
    assert.deepEqual(audit.list(), ['Hello', 'World'], 'blank and numeric text needs no translation');
});
