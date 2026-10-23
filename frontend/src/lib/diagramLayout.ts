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
  const BASE_WIDTH = narrow ? 600 : 960,
    CARD_W = narrow ? 172 : 214,
    GAP = narrow ? 14 : 22;
  const perRow = Math.max(1, Math.floor((BASE_WIDTH - GAP) / (CARD_W + GAP)));
  const margin = (BASE_WIDTH - (perRow * CARD_W + (perRow - 1) * GAP)) / 2;
  const rows = Math.max(1, Math.ceil(count / perRow));
  const sideChannels = (rows - 1) * Math.ceil(perRow / 2);
  const WIDTH = BASE_WIDTH + 2 * Math.max(0, (sideChannels ? sideChannels * 6 + 24 : 0) - margin);
  const rowTop = ROW_TOP;
  const rowGap = 64;
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
    const y = rowTop + row * (CARD_H + rowGap);
    cards.push({ x, y, w: CARD_W, h: CARD_H, cx: x + CARD_W / 2, cy: y + CARD_H / 2 });
  }
  return { width: WIDTH, height: rowTop + rows * CARD_H + (rows - 1) * rowGap + 16, coordinator, cards };
}

/** Sample rounded corners so the visible wire and its packets share precisely the same route. */
function roundRoute(points: Point[]): Point[] {
  const route = [points[0]];
  for (let index = 1; index < points.length - 1; index++) {
    const previous = points[index - 1],
      corner = points[index],
      next = points[index + 1];
    const before = Math.hypot(corner.x - previous.x, corner.y - previous.y);
    const after = Math.hypot(next.x - corner.x, next.y - corner.y);
    const radius = Math.min(12, before / 2, after / 2);
    if (!radius) continue;
    const enter = {
      x: corner.x + ((previous.x - corner.x) * radius) / before,
      y: corner.y + ((previous.y - corner.y) * radius) / before,
    };
    const leave = {
      x: corner.x + ((next.x - corner.x) * radius) / after,
      y: corner.y + ((next.y - corner.y) * radius) / after,
    };
    route.push(enter);
    for (let step = 1; step <= 8; step++) route.push(bezierPoint(enter, corner, corner, leave, step / 8));
  }
  route.push(points[points.length - 1]);
  return route;
}

/** First-row GPUs connect directly; lower rows use the nearest outer edge and empty row gutters. */
export function workerRoute(layout: DiagramLayout, index: number): Point[] {
  const card = layout.cards[index];
  if (!card) throw new RangeError('Unknown worker card');
  const c = layout.coordinator;
  const target = { x: card.cx, y: card.y };
  const firstRow = layout.cards[0].y;
  if (card.y === firstRow) {
    const curve = connector({ x: c.cx, y: c.y + c.h }, target);
    return Array.from({ length: 33 }, (_, step) => bezierPoint(...curve, step / 32));
  }
  const left = card.cx < c.cx;
  const side = layout.cards.filter((other) => other.y > firstRow && other.cx < c.cx === left);
  const outside = (other: Card) => Math.abs(other.cx - c.cx) > Math.abs(card.cx - c.cx);
  const lane = side.filter((other) => other.y < card.y || (other.y === card.y && outside(other))).length;
  const column = side.filter((other) => other.y === card.y && outside(other)).length;
  const source = { x: left ? c.x : c.x + c.w, y: c.y + 16 + ((lane + 0.5) * (c.h - 32)) / side.length };
  const rail = left ? 12 + lane * 6 : layout.width - 12 - lane * 6;
  const approach = card.y - 24 - column * 8;
  return roundRoute([source, { x: rail, y: source.y }, { x: rail, y: approach }, { x: card.cx, y: approach }, target]);
}

/** Constant-distance travel along precisely the same polyline used by the SVG. */
export function routePosition(route: Point[], progress: number): Point {
  if (progress >= 1) return { ...route[route.length - 1] };
  const lengths = route.slice(1).map((point, i) => Math.hypot(point.x - route[i].x, point.y - route[i].y));
  let distance = Math.max(0, Math.min(1, progress)) * lengths.reduce((a, b) => a + b, 0);
  for (let i = 0; i < lengths.length; i++) {
    if (distance <= lengths[i] && lengths[i] > 0) {
      const t = distance / lengths[i];
      return { x: route[i].x + (route[i + 1].x - route[i].x) * t, y: route[i].y + (route[i + 1].y - route[i].y) * t };
    }
    distance -= lengths[i];
  }
  return { ...route[route.length - 1] };
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

/** A device name cut to fit its label. */
export function shortName(name: string, max: number): string {
  return name.length > max ? name.slice(0, max - 1) + '…' : name;
}
