// Geometry for the live diagram and the timeline chart: plain numbers in, plain numbers out.
export type Point = { x: number; y: number };
export type Card = { x: number; y: number; w: number; h: number; cx: number; cy: number };
export type DiagramLayout = { width: number; height: number; coordinator: Card; cards: Card[] };

const CARD_H = 156;
const COORD_W = 300,
  COORD_H = 86,
  COORD_Y = 14,
  ROW_TOP = 172;

/** `narrow` is for small spaces (the home page): a smaller canvas so the text stays readable when it is scaled down to fit. */
export function layoutWorkers(count: number, narrow = false): DiagramLayout {
  const WIDTH = narrow ? 600 : 960,
    CARD_W = narrow ? 172 : 214,
    GAP = narrow ? 14 : 22;
  const perRow = Math.max(1, Math.floor((WIDTH - GAP) / (CARD_W + GAP)));
  const rows = Math.max(1, Math.ceil(count / perRow));
  const coordinator: Card = {
    x: (WIDTH - COORD_W) / 2,
    y: COORD_Y,
    w: COORD_W,
    h: COORD_H,
    cx: WIDTH / 2,
    cy: COORD_Y + COORD_H / 2,
  };
  const cards: Card[] = [];
  for (let index = 0; index < count; index++) {
    const row = Math.floor(index / perRow);
    const inRow = Math.min(perRow, count - row * perRow);
    const rowWidth = inRow * CARD_W + (inRow - 1) * GAP;
    const x = (WIDTH - rowWidth) / 2 + (index % perRow) * (CARD_W + GAP);
    const y = ROW_TOP + row * (CARD_H + GAP);
    cards.push({ x, y, w: CARD_W, h: CARD_H, cx: x + CARD_W / 2, cy: y + CARD_H / 2 });
  }
  return { width: WIDTH, height: ROW_TOP + rows * CARD_H + (rows - 1) * GAP + 16, coordinator, cards };
}

export function bezierPoint(p0: Point, p1: Point, p2: Point, p3: Point, t: number): Point {
  const u = 1 - t;
  const mix = (a: number, b: number, c: number, d: number) =>
    u * u * u * a + 3 * u * u * t * b + 3 * u * t * t * c + t * t * t * d;
  return { x: mix(p0.x, p1.x, p2.x, p3.x), y: mix(p0.y, p1.y, p2.y, p3.y) };
}

/** The curve a connector follows from the coordinator's bottom edge to a worker card's top edge. */
export function connector(from: Point, to: Point): [Point, Point, Point, Point] {
  const bend = Math.max(36, (to.y - from.y) * 0.45);
  return [from, { x: from.x, y: from.y + bend }, { x: to.x, y: to.y - bend }, to];
}

/** Where a packet is: dispatches travel coordinator → worker, results and failures worker → coordinator. */
export function packetPosition(
  kind: 'dispatch' | 'result' | 'failed',
  progress: number,
  from: Point,
  to: Point,
): Point {
  const [p0, p1, p2, p3] = connector(from, to);
  const t = Math.max(0, Math.min(1, kind === 'dispatch' ? progress : 1 - progress));
  return bezierPoint(p0, p1, p2, p3, t);
}

const STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600, 7200, 21600, 86400].map((s) => s * 1000);

/** Round tick positions (ms) inside [start, end], at most about `max` of them. */
export function niceTicks(startMs: number, endMs: number, max: number): number[] {
  const span = endMs - startMs;
  if (!(span > 0)) return [startMs];
  const step = STEPS.find((s) => span / s <= max) ?? STEPS.at(-1)!;
  const first = Math.ceil(startMs / step) * step;
  const ticks: number[] = [];
  for (let t = first; t <= endMs && ticks.length < 200; t += step) ticks.push(t);
  return ticks;
}

export function candidateLabel(id: string | null | undefined): string {
  if (!id) return '–';
  const last = id.split('.').at(-1) ?? id;
  return last;
}

export function formatDuration(ms: number): string {
  const total = Math.max(0, ms) / 1000;
  if (total < 60) return total === 0 ? '0 s' : `${total.toFixed(1)} s`;
  const seconds = Math.floor(total % 60),
    minutes = Math.floor(total / 60) % 60,
    hours = Math.floor(total / 3600);
  const two = (n: number) => String(n).padStart(2, '0');
  return hours ? `${hours}:${two(minutes)}:${two(seconds)}` : `${minutes}:${two(seconds)}`;
}
