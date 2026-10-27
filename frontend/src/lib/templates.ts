import type { Experiment } from '../types/experiment';

// Settings a saved template may hold (mirrors backend/templates.py); everything else about a run is chosen again.
const KEYS = [
  'task',
  'maxGenerations',
  'candidatesPerGeneration',
  'alpha',
  'sigma',
  'decodeEngine',
  'schedulerPolicy',
  'syncMode',
  'workerIds',
  'recipeVersion',
  'weightSpace',
  'antithetic',
  'scorer',
  'coefficientRule',
  'systemPrompt',
  'validationInterval',
  'auditRate',
  'hardCapSeconds',
  'stallSeconds',
  'batchSize',
  'batchSeed',
  'sigmaSchedule',
  'sigmaMinimum',
  'maxNewTokens',
  'alphaSchedule',
  'alphaMinimum',
  'momentumBeta',
  'momentumWindow',
  'evalChunk',
  'sampler',
  'candidateSeedNamespace',
] as const;

export type TemplateConfig = Partial<Pick<Experiment, (typeof KEYS)[number]>> & {
  backupPolicy?: { interval: number; retain: number };
};
export type Template = {
  templateId: string;
  name: string;
  config: TemplateConfig;
  ownerName?: string;
  ownerUserId?: string;
  builtIn?: boolean;
};

/** The settings of a finished or running experiment that make sense to reuse. */
export function templateConfigFromExperiment(experiment: Experiment): TemplateConfig {
  const config: Record<string, unknown> = {};
  for (const key of KEYS) {
    const value = experiment[key];
    if (value !== undefined && (value !== null || key === 'systemPrompt')) config[key] = structuredClone(value);
  }
  if (experiment.backupPolicy)
    config.backupPolicy = { interval: experiment.backupPolicy.interval, retain: experiment.backupPolicy.retain };
  return config as TemplateConfig;
}

export const BUILT_IN: Template[] = [
  {
    templateId: 'built-in-smoke',
    name: 'Quick smoke test (1 generation, 4 candidates)',
    builtIn: true,
    config: { maxGenerations: 1, candidatesPerGeneration: 4 },
  },
  {
    templateId: 'built-in-demo',
    name: 'Demo run (3 generations, 12 candidates)',
    builtIn: true,
    config: { maxGenerations: 3, candidatesPerGeneration: 12 },
  },
  {
    templateId: 'built-in-gpu-comparison',
    name: 'GPU comparison (5 generations, 16 candidates)',
    builtIn: true,
    config: { maxGenerations: 5, candidatesPerGeneration: 16 },
  },
];

/** What the experiment wizard starts from: a clone of a run, or a template's settings under the template's name. */
export function wizardStart(options: {
  clone?: Experiment;
  template?: Template;
  defaults?: Partial<Experiment>;
}): Partial<Experiment> | undefined {
  if (options.clone)
    return { ...options.clone, name: copyName(options.clone.name), status: 'DRAFT' as Experiment['status'] };
  if (options.template)
    return {
      ...(options.defaults ?? {}),
      ...(options.template.config as Partial<Experiment>),
      name: options.template.builtIn ? '' : options.template.name,
    };
  return undefined;
}

export function copyName(name: string): string {
  const trimmed = name.replace(/\s*\(copy(?: \d+)?\)$/, '').trim();
  const next = `${trimmed} (copy)`;
  return next.length > 160 ? next.slice(next.length - 160) : next;
}
