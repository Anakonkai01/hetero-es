import type { V3Settings } from '../types/experiment';

export const DEFAULT_V3: V3Settings = {
  weightSpace: { kind: 'full' },
  antithetic: false,
  coefficientRule: 'zscore@1',
  systemPrompt: null,
  alphaSchedule: 'constant',
  alphaMinimum: null,
  momentumBeta: null,
  momentumWindow: 4,
  evalChunk: null,
  scorer: {
    kind: 'declarative',
    name: 'exact-string',
    version: 1,
    codeSha256: null,
    config: { answerField: 'answer', strip: true, casefold: false },
  },
};

/** Choosing a decaying alpha needs an end value: a tenth of alpha unless one was already chosen (it cannot exceed alpha). */
export function withAlphaSchedule(settings: V3Settings, schedule: string, alpha: number): V3Settings {
  if (schedule === 'constant') return { ...settings, alphaSchedule: schedule, alphaMinimum: null };
  const minimum = settings.alphaMinimum ?? Number((alpha / 10).toPrecision(3));
  return { ...settings, alphaSchedule: schedule, alphaMinimum: minimum };
}

/** What the review step lists for a Recipe v3 experiment: every ES choice the researcher made, as label and value. */
export function v3ReviewRows(
  settings: V3Settings,
  run: {
    dataset: string;
    batchSize: number;
    batchSeed: number;
    sigma: number;
    sigmaSchedule: string;
    sigmaMinimum: number;
    alpha: number;
    maxNewTokens: number;
  },
): [string, string][] {
  const space = settings.weightSpace;
  return [
    ['Dataset', run.dataset],
    ['Batch', `${run.batchSize} · seed ${run.batchSeed}`],
    [
      'Sigma',
      run.sigmaSchedule === 'constant' ? `${run.sigma}` : `${run.sigma} → ${run.sigmaMinimum} (${run.sigmaSchedule})`,
    ],
    [
      'Alpha',
      settings.alphaSchedule === 'constant'
        ? `${run.alpha}`
        : `${run.alpha} → ${settings.alphaMinimum} (${settings.alphaSchedule})`,
    ],
    ['Coefficient rule', settings.coefficientRule],
    ['Momentum', settings.momentumBeta === null ? '—' : `β ${settings.momentumBeta} · ${settings.momentumWindow}`],
    ['Antithetic sampling', settings.antithetic ? 'ON' : 'OFF'],
    ['Weight space', space.kind === 'lora' ? `LoRA r${space.rank}` : space.kind],
    ['Declarative scorer', `${settings.scorer.name}@${settings.scorer.version}`],
    ['Maximum output tokens', `${run.maxNewTokens}`],
    ['Prompts per generate() call', `${settings.evalChunk ?? 16}`],
  ];
}
