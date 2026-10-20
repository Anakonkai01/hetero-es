import { StepHeader, useProduct } from '@heteroes/product-ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import { apiGet } from '../../api/client';
import { useScopeKey } from '../../app/session';
import { useWorkers } from '../../hooks/useWorkers';
import { V3Fields } from './V3Fields';
import { DEFAULT_V3, v3ReviewRows } from '../../lib/v3Settings';
import type { V3Settings } from '../../types/experiment';
import type { CreateExperimentRequest, Experiment } from '../../types/experiment';
import type { StudyDataset, StudyModel } from './StudyAssets';
interface Capabilities {
  coordinatorDevices?: {
    deviceId: string;
    workerId: string;
    displayName?: string;
    platform?: string;
    updateSecondsPerSeed?: number | null;
  }[];
  defaultCoordinatorDeviceId?: string | null;
  modelId: string;
  modelRevision: string;
  workloads: string[];
  schedulerPolicies: string[];
  syncModes: string[];
  workerIds: string[];
}
export function RuntimeConfiguration({
  initial,
  onSave,
  pending,
}: {
  initial?: Experiment;
  onSave: (value: CreateExperimentRequest) => Promise<unknown>;
  pending: boolean;
}) {
  const { t } = useProduct();
  const [step, setStep] = useState(0);
  const scope = useScopeKey();
  const workers = useWorkers();
  const cap = useQuery({
    queryKey: ['capabilities', ...scope],
    queryFn: () => apiGet<Capabilities>('/api/v1/capabilities'),
    enabled: scope.every(Boolean),
  });
  // the lab's default coordinator is pre-selected; the creator can still choose another one
  const defaultCoordinator = cap.data?.defaultCoordinatorDeviceId;
  const [name, setName] = useState(initial?.name ?? '');
  const [task, setTask] = useState(initial?.task ?? 'arith16');
  const [generations, setGenerations] = useState(initial?.maxGenerations ?? 3);
  const [candidates, setCandidates] = useState(initial?.candidatesPerGeneration ?? 8);
  const [alpha, setAlpha] = useState(initial?.alpha ?? 0.001);
  const [sigma, setSigma] = useState(initial?.sigma ?? 0.001);
  const [decoder, setDecoder] = useState(initial?.decodeEngine ?? 'hf_generate');
  const [selected, setSelected] = useState<string[]>(initial?.workerIds ?? []);
  const [coordinatorChoice, setCoordinator] = useState(initial?.coordinatorDeviceId);
  const coordinator = coordinatorChoice ?? defaultCoordinator ?? '';
  const [interval, setInterval] = useState(initial?.backupPolicy?.interval ?? 1);
  const [retain, setRetain] = useState(initial?.backupPolicy?.retain ?? 3);
  const [error, setError] = useState('');
  const [v3, setV3] = useState<V3Settings>({
    weightSpace: initial?.weightSpace ?? DEFAULT_V3.weightSpace,
    antithetic: initial?.antithetic ?? false,
    scorer: initial?.scorer ?? DEFAULT_V3.scorer,
    coefficientRule: initial?.coefficientRule ?? 'zscore@1',
    systemPrompt: initial?.systemPrompt ?? null,
    promptFormat: initial?.promptFormat ?? null,
    pythonCode: initial?.pythonCode ?? [],
    alphaSchedule: initial?.alphaSchedule ?? DEFAULT_V3.alphaSchedule,
    alphaMinimum: initial?.alphaMinimum ?? DEFAULT_V3.alphaMinimum,
    momentumBeta: initial?.momentumBeta ?? DEFAULT_V3.momentumBeta,
    momentumWindow: initial?.momentumWindow ?? DEFAULT_V3.momentumWindow,
    evalChunk: initial?.evalChunk ?? DEFAULT_V3.evalChunk,
    sampler: initial?.sampler ?? DEFAULT_V3.sampler,
    candidateSeedNamespace: initial?.candidateSeedNamespace ?? null,
  });
  const [validationInterval, setValidationInterval] = useState(initial?.validationInterval ?? 1);
  const [version, setVersion] = useState(initial?.recipeVersion ?? 1);
  const [modelId, setModelId] = useState(initial?.modelArtifactId ?? '');
  const [datasetId, setDatasetId] = useState(initial?.datasetIds?.[0] ?? '');
  const [batchSize, setBatchSize] = useState(initial?.batchSize ?? 32);
  const [batchSeed, setBatchSeed] = useState(initial?.batchSeed ?? 11);
  const [schedule, setSchedule] = useState(initial?.sigmaSchedule ?? 'constant');
  const [minimum, setMinimum] = useState(initial?.sigmaMinimum ?? 0.00025);
  const [maxTokens, setMaxTokens] = useState(initial?.maxNewTokens ?? 512);
  const modelList = useQuery({
    queryKey: ['study-models', ...scope],
    queryFn: () => apiGet<StudyModel[]>('/api/v1/models'),
    enabled: scope.every(Boolean),
  });
  const dataList = useQuery({
    queryKey: ['study-datasets', ...scope],
    queryFn: () => apiGet<StudyDataset[]>('/api/v1/datasets'),
    enabled: scope.every(Boolean),
  });
  const customModel = modelList.data?.find((m) => m.modelArtifactId === modelId);
  const available = workers.data ?? [];
  return (
    <form
      className="cb demo-form"
      onSubmit={(event) => {
        event.preventDefault();
        setError('');
        if (version === 3 && v3.antithetic && candidates % 2) {
          setError(t('Antithetic sampling needs an even number of candidates.'));
          return;
        }
        if (step === 0) {
          if (name.trim().length < 3) {
            setError(t('Enter an experiment name.'));
            return;
          }
          setStep(1);
          return;
        }
        if (!cap.data || !selected.length || !coordinator) {
          setError(t('Select workers and a coordinator.'));
          return;
        }
        if (step === 1) {
          setStep(2);
          return;
        }
        if (version >= 2 && (!customModel?.manifest || !datasetId)) {
          setError(t('Select a pinned model and frozen dataset.'));
          return;
        }
        void onSave({
          name,
          modelName: version >= 2 ? customModel!.reference : cap.data.modelId,
          modelArtifactId: version >= 2 ? modelId : 'qwen-pinned',
          task: version === 3 ? 'text_v3' : version === 2 ? 'text_math_v2' : task,
          ...(version >= 2
            ? {
                recipeVersion: version,
                datasetIds: [datasetId],
                batchSize,
                batchSeed,
                sigmaSchedule: schedule,
                sigmaMinimum: minimum,
                maxNewTokens: maxTokens,
                validationInterval,
                ...(version === 3 ? v3 : {}),
              }
            : {}),
          maxGenerations: generations,
          candidatesPerGeneration: candidates,
          alpha,
          sigma,
          decodeEngine: decoder,
          coordinatorDeviceId: coordinator,
          backupPolicy: { interval, retain },
          workerIds: selected,
          schedulerPolicy: 'greedy',
          syncMode: 'synchronous',
        }).catch((e: Error) => setError(e.message));
      }}
    >
      <StepHeader steps={['Setup', 'Resources', 'Review']} current={step} />
      {cap.isError && (
        <p className="note err" role="alert">
          {t('Runtime capabilities unavailable. Check the control service.')}
        </p>
      )}
      {step === 0 && (
        <section className="setup-section">
          <h2>{t('Set up your experiment')}</h2>
          <p className="hint">{t('Choose a workload and experiment size. Technical settings are optional.')}</p>
          <div className="setup-grid">
            <label className="fg">
              {t('Experiment name')}
              <input
                autoFocus
                className="inp"
                required
                minLength={3}
                maxLength={160}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="fg">
              {t('Experiment recipe')}
              <select
                className="sel"
                value={version}
                onChange={(e) => {
                  setVersion(Number(e.target.value));
                  setDecoder('hf_generate');
                }}
              >
                <option value={1}>{t('Built-in workload · Recipe v1')}</option>
                <option value={2}>{t('Math dataset · Recipe v2')}</option>
                <option value={3}>{t('Custom experiment · Recipe v3')}</option>
              </select>
            </label>
            {version === 1 && (
              <label className="fg">
                {t('Workload')}
                <select
                  className="sel"
                  value={task}
                  onChange={(e) => {
                    setTask(e.target.value);
                    if (e.target.value === 'arith16') setDecoder('hf_generate');
                  }}
                >
                  {cap.data?.workloads.map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
            )}
            <label className="fg">
              {t('Maximum generations')}
              <input
                className="inp"
                type="number"
                required
                min={1}
                max={1000}
                value={generations}
                onChange={(e) => setGenerations(Number(e.target.value))}
              />
            </label>
            <label className="fg">
              {t('Candidates per generation')}
              <input
                className="inp"
                type="number"
                required
                min={2}
                max={256}
                value={candidates}
                onChange={(e) => setCandidates(Number(e.target.value))}
              />
            </label>
          </div>
          {version >= 2 && (
            <div className="setup-grid">
              <label className="fg">
                {t('Pinned model')}
                <select className="sel" required value={modelId} onChange={(e) => setModelId(e.target.value)}>
                  <option value="">{t('Select model')}</option>
                  {modelList.data
                    ?.filter((m) => m.manifest && ['REGISTERED', 'READY'].includes(m.status))
                    .map((m) => (
                      <option key={m.modelArtifactId} value={m.modelArtifactId}>
                        {m.name} · {m.revision}
                      </option>
                    ))}
                </select>
              </label>
              <label className="fg">
                {t('Frozen dataset')}
                <select className="sel" required value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
                  <option value="">{t('Select dataset')}</option>
                  {dataList.data
                    ?.filter((d) => (d.recipeVersion ?? 2) === version)
                    .map((d) => (
                      <option key={d.datasetId} value={d.datasetId}>
                        {d.name} · {d.counts.train}/{d.counts.validation}/{d.counts.test}
                      </option>
                    ))}
                </select>
              </label>
              <label className="fg">
                {t('Batch size')}
                <input
                  className="inp"
                  type="number"
                  required
                  min={1}
                  max={1024}
                  value={batchSize}
                  onChange={(e) => setBatchSize(Number(e.target.value))}
                />
              </label>
              <label className="fg">
                {t('Batch seed')}
                <input
                  className="inp"
                  type="number"
                  required
                  min={0}
                  value={batchSeed}
                  onChange={(e) => setBatchSeed(Number(e.target.value))}
                />
              </label>
              <label className="fg">
                {t('Sigma schedule')}
                <select className="sel" value={schedule} onChange={(e) => setSchedule(e.target.value)}>
                  <option value="constant">constant</option>
                  <option value="cosine">cosine</option>
                </select>
              </label>
              <label className="fg">
                {t('Minimum sigma')}
                <input
                  className="inp"
                  type="number"
                  required
                  min={1e-7}
                  max={sigma}
                  step="any"
                  value={minimum}
                  onChange={(e) => setMinimum(Number(e.target.value))}
                />
              </label>
              <label className="fg">
                {t('Maximum output tokens')}
                <input
                  className="inp"
                  type="number"
                  required
                  min={1}
                  max={2048}
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(Number(e.target.value))}
                />
              </label>
              <Link className="link" to="/models">
                {t('Import models and datasets')}
              </Link>
            </div>
          )}
          {version === 3 && <V3Fields value={v3} onChange={setV3} alpha={alpha} />}
          {version >= 2 && (
            <label className="fg">
              {t('Validation interval')}
              <input
                className="inp"
                type="number"
                required
                min={1}
                max={1000}
                value={validationInterval}
                onChange={(e) => setValidationInterval(Number(e.target.value))}
              />
            </label>
          )}
          <p className="hint">
            {version >= 2 ? customModel?.reference : cap.data?.modelId} · {t('Pinned runtime model')}
          </p>
          <details className="advanced-panel">
            <summary>{t('Advanced settings')}</summary>
            <div className="setup-grid">
              <label className="fg">
                {t('Alpha')}
                <input
                  className="inp"
                  type="number"
                  required
                  min={0.0000001}
                  max={1}
                  step="any"
                  value={alpha}
                  onChange={(e) => setAlpha(Number(e.target.value))}
                />
              </label>
              <label className="fg">
                {t('Sigma')}
                <input
                  className="inp"
                  type="number"
                  required
                  min={0.0000001}
                  max={1}
                  step="any"
                  value={sigma}
                  onChange={(e) => setSigma(Number(e.target.value))}
                />
              </label>
              <label className="fg">
                {t('Decoder')}
                <select className="sel" value={decoder} onChange={(e) => setDecoder(e.target.value)}>
                  <option>{t('hf_generate')}</option>
                  {(version === 3 || (version === 1 && task !== 'arith16')) && <option>{t('hf_compact')}</option>}
                </select>
              </label>
              <p className="hint">{t('FP32 evaluation · canonical CPU noise · exact worker restore.')}</p>
              <p className="hint">
                {t('Pinned revision:')} {cap.data?.modelRevision}
              </p>
            </div>
          </details>
        </section>
      )}
      {step === 1 && (
        <section className="setup-section">
          <h2>{t('Choose your GPU resources')}</h2>
          <p className="hint">
            {t(
              'Jobs wait in the queue while selected devices are offline or contribution is OFF. Closing the browser does not cancel the job.',
            )}
          </p>
          <label className="fg">
            {t('Coordinator')}
            <select className="sel" required value={coordinator} onChange={(e) => setCoordinator(e.target.value)}>
              <option value="">{t('Select coordinator')}</option>
              {cap.data?.coordinatorDevices?.map((d) => (
                <option key={d.deviceId} value={d.deviceId}>
                  {d.displayName ?? d.workerId}
                </option>
              ))}
            </select>
          </label>
          {(() => {
            // the update of a generation: one noise pass per seed (momentum adds earlier generations' seeds)
            const chosen = cap.data?.coordinatorDevices?.find((d) => d.deviceId === coordinator);
            if (!chosen?.updateSecondsPerSeed) return null;
            const seeds = version === 3 && v3.momentumBeta ? candidates * v3.momentumWindow : candidates;
            return (
              <p className="hint">
                {t('Update on this coordinator: about')} {Math.ceil(chosen.updateSecondsPerSeed * seeds)}{' '}
                {t('s per generation')}
              </p>
            );
          })()}
          <fieldset className="worker-picker">
            <legend>{t('Configured workers')}</legend>
            {workers.isError && <p role="alert">{t('Worker status unavailable')}</p>}
            {available.map((worker) => (
              <label className={selected.includes(worker.workerId) ? 'selected' : ''} key={worker.workerId}>
                <input
                  type="checkbox"
                  checked={selected.includes(worker.workerId)}
                  onChange={() =>
                    setSelected((ids) =>
                      ids.includes(worker.workerId)
                        ? ids.filter((id) => id !== worker.workerId)
                        : [...ids, worker.workerId],
                    )
                  }
                />
                <div>
                  <b>{worker.profile.gpuName}</b>
                  <small>
                    {worker.displayName ?? worker.workerId} · {t(worker.status)} ·{' '}
                    {t(worker.contributionEnabled === false ? 'OFF' : 'ON')}
                  </small>
                </div>
              </label>
            ))}
            {selected
              .filter((id) => !available.some((w) => w.workerId === id))
              .map((id) => (
                <label key={id}>
                  <input
                    type="checkbox"
                    checked
                    onChange={() => setSelected((ids) => ids.filter((value) => value !== id))}
                  />
                  {id} · {t('No longer available')}
                </label>
              ))}
          </fieldset>
        </section>
      )}
      {step === 2 && (
        <section className="setup-section">
          <h2>{t('Review before saving')}</h2>
          <dl className="setup-review">
            <div>
              <dt>{t('Experiment name')}</dt>
              <dd>{name}</dd>
            </div>
            <div>
              <dt>{t('Workload')}</dt>
              <dd>{version === 3 ? t('Custom experiment · Recipe v3') : version === 2 ? 'text_math_v2' : task}</dd>
            </div>
            <div>
              <dt>{t('Generations')}</dt>
              <dd>
                {generations} × {candidates} {t('candidates')}
              </dd>
            </div>
            <div>
              <dt>{t('Workers')}</dt>
              <dd>{selected.map((id) => available.find((w) => w.workerId === id)?.displayName ?? id).join(', ')}</dd>
            </div>
            <div>
              <dt>{t('Coordinator')}</dt>
              <dd>
                {(() => {
                  const device = cap.data?.coordinatorDevices?.find((d) => d.deviceId === coordinator);
                  return device ? (device.displayName ?? device.workerId) : t('Local coordinator');
                })()}
              </dd>
            </div>
            <div>
              <dt>{t('Model')}</dt>
              <dd>{version >= 2 ? customModel?.reference : cap.data?.modelId}</dd>
            </div>
            {version === 3 &&
              v3ReviewRows(v3, {
                dataset: dataList.data?.find((d) => d.datasetId === datasetId)?.name ?? datasetId,
                batchSize,
                batchSeed,
                sigma,
                sigmaSchedule: schedule,
                sigmaMinimum: minimum,
                alpha,
                maxNewTokens: maxTokens,
              }).map(([label, value]) => (
                <div key={label}>
                  <dt>{t(label)}</dt>
                  <dd>{t(value)}</dd>
                </div>
              ))}
          </dl>
          <details className="advanced-panel">
            <summary>{t('Backup policy')}</summary>
            <div className="setup-grid">
              <label className="fg">
                {t('Backup every K generations')}
                <input
                  className="inp"
                  type="number"
                  required
                  min={1}
                  max={1000}
                  value={interval}
                  onChange={(e) => setInterval(Number(e.target.value))}
                />
              </label>
              <label className="fg">
                {t('Keep N recovery points')}
                <input
                  className="inp"
                  type="number"
                  required
                  min={1}
                  max={1000}
                  value={retain}
                  onChange={(e) => setRetain(Number(e.target.value))}
                />
              </label>
            </div>
          </details>
          <p className="note">{t('Saving creates a draft. Submit it from the experiment page when ready.')}</p>
        </section>
      )}
      {error && (
        <p className="note err" role="alert">
          {error}
        </p>
      )}
      <footer className="setup-footer">
        <button
          type="button"
          className="btn"
          disabled={step === 0 || pending}
          onClick={() => {
            setError('');
            setStep(step - 1);
          }}
        >
          {t('Back')}
        </button>
        <button className="btn pri" disabled={pending || !cap.data}>
          {t(step === 2 ? 'Save draft' : 'Continue')}
        </button>
      </footer>
    </form>
  );
}
