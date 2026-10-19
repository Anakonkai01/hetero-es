import { test } from 'node:test';
import assert from 'node:assert/strict';
import { templateConfigFromExperiment, wizardStart, copyName, BUILT_IN } from '../src/lib/templates.ts';

const run = {
  experimentId: 'abc',
  name: 'Demo run',
  status: 'COMPLETED',
  task: 'arith16',
  maxGenerations: 3,
  candidatesPerGeneration: 12,
  alpha: 0.001,
  sigma: 0.001,
  decodeEngine: 'hf_generate',
  schedulerPolicy: 'greedy',
  syncMode: 'synchronous',
  workerIds: ['a', 'b'],
  backupPolicy: { interval: 1, retain: 3 },
  datasetIds: ['d'],
  modelArtifactId: 'm',
  coordinatorDeviceId: 'c',
  ownerUserId: 'u',
  createdAt: 'x',
  configHash: 'h',
};

test('a template keeps the reusable settings and never ids that can go stale', () => {
  const config = templateConfigFromExperiment(run);
  assert.deepEqual(Object.keys(config).sort(), [
    'alpha',
    'backupPolicy',
    'candidatesPerGeneration',
    'decodeEngine',
    'maxGenerations',
    'schedulerPolicy',
    'sigma',
    'syncMode',
    'task',
    'workerIds',
  ]);
  for (const stale of [
    'datasetIds',
    'modelArtifactId',
    'coordinatorDeviceId',
    'ownerUserId',
    'experimentId',
    'name',
    'status',
  ])
    assert.ok(!(stale in config), stale);
  assert.notEqual(config.workerIds, run.workerIds, 'the lists are copies');
  assert.deepEqual(
    templateConfigFromExperiment({ ...run, alpha: undefined, workerIds: undefined, backupPolicy: undefined }).alpha,
    undefined,
  );
});

test('cloning keeps every setting, gives a draft a "(copy)" name and never copies the old run\'s results', () => {
  const start = wizardStart({
    clone: { ...run, completedGenerations: 3, committedCandidateCount: 12, failureReason: 'x' },
  });
  assert.equal(start.name, 'Demo run (copy)');
  assert.equal(start.status, 'DRAFT');
  assert.equal(start.candidatesPerGeneration, 12);
  assert.deepEqual(start.workerIds, ['a', 'b']);
});

test('names of copies do not pile up', () => {
  assert.equal(copyName('Demo run'), 'Demo run (copy)');
  assert.equal(copyName('Demo run (copy)'), 'Demo run (copy)');
  assert.equal(copyName('Demo run (copy 2)'), 'Demo run (copy)');
  assert.ok(copyName('x'.repeat(300)).length <= 160);
});

test('a template starts the wizard with its settings; a built-in one leaves the name to the person', () => {
  const saved = { templateId: 't', name: 'My 3x12', config: { maxGenerations: 3, candidatesPerGeneration: 12 } };
  assert.deepEqual(wizardStart({ template: saved }), {
    maxGenerations: 3,
    candidatesPerGeneration: 12,
    name: 'My 3x12',
  });
  assert.equal(wizardStart({ template: BUILT_IN[0] }).name, '');
  assert.equal(wizardStart({ template: BUILT_IN[0] }).maxGenerations, 1);
  assert.equal(wizardStart({}), undefined);
});

test('the built-in templates stay inside what the backend accepts', () => {
  for (const { config } of BUILT_IN) {
    assert.ok(config.maxGenerations >= 1 && config.maxGenerations <= 1000);
    assert.ok(config.candidatesPerGeneration >= 2 && config.candidatesPerGeneration <= 256);
  }
  assert.equal(new Set(BUILT_IN.map((t) => t.templateId)).size, BUILT_IN.length);
});

test('a v3 template retains declarative settings without retaining artifact ids', () => {
  const options = {
    weightSpace: { kind: 'lora', rank: 4, alpha: 8, targetModules: ['q_proj'] },
    antithetic: true,
    coefficientRule: 'centered-rank@1',
    systemPrompt: null,
    alphaSchedule: 'cosine',
    alphaMinimum: 0.0001,
    momentumBeta: 0.875,
    momentumWindow: 3,
    evalChunk: 64,
    scorer: {
      kind: 'declarative',
      name: 'choice-letter',
      version: 1,
      codeSha256: null,
      config: { answerField: 'label' },
    },
  };
  const saved = templateConfigFromExperiment({ ...run, recipeVersion: 3, ...options });
  for (const [key, value] of Object.entries(options)) assert.deepEqual(saved[key], value);
  assert.equal(saved.modelArtifactId, undefined);
  assert.equal(saved.datasetIds, undefined);
});
