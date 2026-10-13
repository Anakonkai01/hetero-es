import { test } from 'node:test';
import assert from 'node:assert/strict';
import { layoutWorkers, bezierPoint, packetPosition, niceTicks, candidateLabel, formatDuration } from '../src/lib/diagramLayout.ts';

test('cards sit in one centred row when they fit and wrap into rows otherwise, never overlapping or leaving the canvas', () => {
    for (const count of [1, 2, 3, 4, 5, 6, 8, 11]) {
        const layout = layoutWorkers(count);
        assert.equal(layout.cards.length, count);
        for (const card of layout.cards) {
            assert.ok(card.x >= 0 && card.x + card.w <= layout.width, `card inside canvas for ${count}`);
            assert.ok(card.y + card.h <= layout.height);
            assert.equal(card.cx, card.x + card.w / 2);
        }
        for (let a = 0; a < count; a++) for (let b = a + 1; b < count; b++) {
            const A = layout.cards[a], B = layout.cards[b];
            const apart = A.x + A.w <= B.x || B.x + B.w <= A.x || A.y + A.h <= B.y || B.y + B.h <= A.y;
            assert.ok(apart, `cards ${a} and ${b} overlap for ${count} workers`);
            if (A.y === B.y) assert.ok(B.x - (A.x + A.w) >= 8 || A.x - (B.x + B.w) >= 8, `cards ${a} and ${b} need a visible gap`);
        }
        assert.ok(layout.coordinator.y + layout.coordinator.h < layout.cards[0].y, 'the coordinator is above every card');
    }
    assert.equal(layoutWorkers(3).cards[0].y, layoutWorkers(3).cards[2].y, 'one row for three workers');
    assert.ok(layoutWorkers(8).cards.at(-1).y > layoutWorkers(8).cards[0].y, 'eight workers wrap');
    const one = layoutWorkers(1);
    assert.equal(one.cards[0].cx, one.width / 2, 'a single card is centred');
});

test('the narrow layout used on the home page keeps three cards in one row on a smaller canvas', () => {
    const wide = layoutWorkers(3), narrow = layoutWorkers(3, true);
    assert.ok(narrow.width < wide.width);
    assert.equal(new Set(narrow.cards.map(c => c.y)).size, 1, 'three cards in one row');
    for (const card of narrow.cards) assert.ok(card.x >= 0 && card.x + card.w <= narrow.width);
    assert.ok(layoutWorkers(5, true).cards.at(-1).y > layoutWorkers(5, true).cards[0].y, 'more than three wrap');
});

test('no workers still gives a drawable canvas', () => {
    const layout = layoutWorkers(0);
    assert.deepEqual(layout.cards, []);
    assert.ok(layout.height > 0 && layout.width > 0);
});

test('a bezier starts and ends at its anchors and a packet travels out and back along the same curve', () => {
    const [p0, p1, p2, p3] = [{ x: 0, y: 0 }, { x: 0, y: 50 }, { x: 100, y: 50 }, { x: 100, y: 100 }];
    assert.deepEqual(bezierPoint(p0, p1, p2, p3, 0), p0);
    assert.deepEqual(bezierPoint(p0, p1, p2, p3, 1), p3);
    const mid = bezierPoint(p0, p1, p2, p3, 0.5);
    assert.equal(mid.x, 50); assert.equal(mid.y, 50);
    const from = { x: 480, y: 100 }, to = { x: 200, y: 300 };
    const out = packetPosition('dispatch', 0.25, from, to), back = packetPosition('result', 0.75, from, to);
    assert.deepEqual(packetPosition('dispatch', 1, from, to), { x: to.x, y: to.y });
    assert.deepEqual(packetPosition('result', 0, from, to), { x: to.x, y: to.y }, 'results start at the worker');
    assert.deepEqual(packetPosition('result', 1, from, to), { x: from.x, y: from.y }, 'and arrive at the coordinator');
    assert.deepEqual(packetPosition('failed', 0.5, from, to), packetPosition('result', 0.5, from, to));
    assert.ok(out.y < back.y + 1 && out.y > from.y);
});

test('axis ticks use round steps, stay inside the range and are few enough to read', () => {
    const ticks = niceTicks(0, 47_000, 8);
    assert.ok(ticks.length >= 3 && ticks.length <= 9, String(ticks.length));
    assert.deepEqual(ticks.slice(0, 3), [0, 10_000, 20_000]);
    assert.ok(ticks.every(t => t >= 0 && t <= 47_000));
    const minutes = niceTicks(0, 11 * 60_000, 8);
    assert.ok(minutes.every(t => t % 60_000 === 0 || t % 30_000 === 0), 'minute-scale runs tick on minutes');
    assert.deepEqual(niceTicks(5, 5, 8), [5], 'an empty range is a single tick');
    assert.deepEqual(niceTicks(10, 0, 8), [10], 'a reversed range does not loop');
});

test('labels are short and durations read naturally', () => {
    assert.equal(candidateLabel('d21c66055d32485cb433f708c772eb07.g0.c3'), 'c3');
    assert.equal(candidateLabel('x'), 'x');
    assert.equal(candidateLabel(null), '–');
    assert.equal(formatDuration(0), '0 s');
    assert.equal(formatDuration(2_350), '2.4 s');
    assert.equal(formatDuration(75_000), '1:15');
    assert.equal(formatDuration(3_725_000), '1:02:05');
    assert.equal(formatDuration(-5), '0 s');
});
