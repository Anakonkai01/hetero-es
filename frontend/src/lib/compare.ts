// Pure helpers for putting several runs side by side.
import type { Experiment } from '../types/experiment';
import type { Generation } from '../types/generation';

export type RunInput = { experiment: Experiment; generations: Generation[] };
export type SeriesPoint = { generation: number; mean: number; best: number };
export type Series = { id: string; name: string; points: SeriesPoint[] };
export type Row = {
  id: string;
  name: string;
  status: string;
  bestReward: number | null;
  lastMean: number | null;
  durationSeconds: number | null;
  workers: string[];
  completedGenerations: number;
  candidatesPerGeneration: number | null;
};
export type Difference = { key: string; values: string[] };

export function runDurationSeconds(experiment: Pick<Experiment, 'startedAt' | 'completedAt'>): number | null {
  if (!experiment.startedAt || !experiment.completedAt) return null;
  const seconds = (Date.parse(experiment.completedAt) - Date.parse(experiment.startedAt)) / 1000;
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

export function compareRuns(runs: RunInput[]): {
  mixedWeightSpaces: boolean;
  series: Series[];
  rows: Row[];
  maxGeneration: number;
  maxReward: number;
} {
  const series: Series[] = runs.map(({ experiment, generations }) => ({
    id: experiment.experimentId,
    name: experiment.name,
    points: generations.flatMap((g, index) =>
      g.rewardMean !== undefined && g.rewardBest !== undefined
        ? [{ generation: index, mean: g.rewardMean, best: g.rewardBest }]
        : [],
    ),
  }));
  const rows: Row[] = runs.map(({ experiment, generations }, i) => {
    const points = series[i].points;
    return {
      id: experiment.experimentId,
      name: experiment.name,
      status: experiment.status,
      bestReward: points.length ? Math.max(...points.map((p) => p.best)) : null,
      lastMean: points.length ? points[points.length - 1].mean : null,
      durationSeconds: runDurationSeconds(experiment),
      workers: experiment.workerIds ?? [],
      completedGenerations: generations.filter((g) => g.status === 'COMPLETED').length,
      candidatesPerGeneration: experiment.candidatesPerGeneration ?? null,
    };
  });
  const mixedWeightSpaces = new Set(runs.map(({ experiment }) => experiment.weightSpace?.kind ?? 'full')).size > 1;
  const all = series.flatMap((s) => s.points);
  return {
    mixedWeightSpaces,
    series: mixedWeightSpaces ? [] : series,
    rows,
    maxGeneration: all.length ? Math.max(...all.map((p) => p.generation)) : 0,
    maxReward: all.length ? Math.max(...all.map((p) => p.best)) : 0,
  };
}

const SETTINGS: (keyof Experiment)[] = [
  'task',
  'modelName',
  'schedulerPolicy',
  'syncMode',
  'candidatesPerGeneration',
  'maxGenerations',
  'alpha',
  'sigma',
  'decodeEngine',
  'workerIds',
  'recipeVersion',
  'weightSpace',
  'antithetic',
  'scorer',
  'coefficientRule',
  'systemPrompt',
  'batchSize',
  'sigmaSchedule',
  'sigmaMinimum',
  'maxNewTokens',
];

const show = (value: unknown): string =>
  Array.isArray(value)
    ? value.join(', ')
    : value === undefined || value === null
      ? '—'
      : typeof value === 'object'
        ? JSON.stringify(value)
        : String(value);

/** The settings that are not the same in every run, in a stable (alphabetical) order. */
export function configDifferences(experiments: Experiment[]): Difference[] {
  if (experiments.length < 2) return [];
  return [...SETTINGS].sort().flatMap((key) => {
    const values = experiments.map((e) => show(e[key]));
    return new Set(values).size > 1 ? [{ key, values }] : [];
  });
}
