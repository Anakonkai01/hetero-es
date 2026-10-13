// Numbers for the "How it works" page, taken from a real finished run (the demo run) and a little geometry for the pictures.
import type { Timeline } from "./runFrame";

/** Rewards as weights for the update: a candidate that did better than average pulls the model towards its noise. */
export function standardize(values: number[]): number[] {
  if (values.length < 2) return values.map(() => 0);
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const spread = Math.sqrt(values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length);
  return spread === 0 ? values.map(() => 0) : values.map(v => (v - mean) / spread);
}

function generator(seed: number) {
  let state = seed >>> 0;
  return () => { state = (state + 0x6d2b79f5) >>> 0; let t = state; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

/** Points scattered around the origin, the same for the same seed: a picture of "many random nudges of the model". */
export function noiseCloud(count: number, seed: number, radius: number): { x: number; y: number }[] {
  const random = generator(seed);
  return Array.from({ length: Math.max(0, count) }, () => { const angle = random() * Math.PI * 2, distance = Math.sqrt(random()) * radius; return { x: Math.cos(angle) * distance, y: Math.sin(angle) * distance }; });
}

export type Explanation = {
  candidates: { name: string; worker: string; reward: number }[]; weights: number[];
  generations: { index: number; mean: number; best: number }[]; totalCandidates: number;
};

export function explainFromTimeline(timeline: Timeline): Explanation {
  const first = timeline.jobs.filter(j => j.generation === 0 && j.status === "SUCCEEDED" && typeof j.reward === "number" && j.workerId);
  const candidates = first.map(j => ({ name: j.candidateId ?? "", worker: j.workerId!, reward: j.reward! }));
  return {
    candidates, weights: standardize(candidates.map(c => c.reward)),
    generations: timeline.generations.filter(g => g.rewardMean !== null && g.rewardBest !== null).map(g => ({ index: g.index, mean: g.rewardMean!, best: g.rewardBest! })),
    totalCandidates: timeline.jobs.filter(j => j.status === "SUCCEEDED").length,
  };
}

const plain = (text: string) => text.replace(/đ/g, "d").replace(/Đ/g, "D").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** Items whose label contains every typed word (accents and case ignored); prefix matches first, the rest in their given order. */
export function commandRank<T extends { label: string }>(items: T[], query: string): T[] {
  const words = plain(query).split(/\s+/).filter(Boolean);
  if (!words.length) return items;
  const scored = items.flatMap((item, index) => {
    const label = plain(item.label);
    if (!words.every(word => label.includes(word))) return [];
    const labelWords = label.split(/\s+/);
    const score = label === words.join(" ") ? 0 : labelWords[0].startsWith(words[0]) ? 1 : labelWords.some(w => w.startsWith(words[0])) ? 2 : 3;
    return [{ item, score, index }];
  });
  return scored.sort((a, b) => a.score - b.score || a.index - b.index).map(entry => entry.item);
}
