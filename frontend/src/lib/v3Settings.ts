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
