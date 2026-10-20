import { useProduct } from '@heteroes/product-ui';
import type { PythonCode, V3Settings, WeightSpace } from '../../types/experiment';
import { withAlphaSchedule } from '../../lib/v3Settings';

const SCORERS = [
  'exact-string',
  'choice-letter',
  'regex',
  'answer-line-last-number',
  'last-integer',
  'answer-line-integer',
  'countdown',
  'boxed-number',
];
const RULES: [string, string][] = [
  ['zscore@1', 'Z-score of the rewards'],
  ['centered-rank@1', 'Centered ranks of the rewards'],
  ['python@1', 'Your Python rule (upload a .py file)'],
];
const PYTHON = '__python__';

/** A .py file and the function to call in it; the lab pins its SHA-256 and runs it on the coordinator only. */
function CodeUpload({
  code,
  onChange,
  fallback,
}: {
  code: PythonCode | undefined;
  onChange: (code: Omit<PythonCode, 'role'>) => void;
  fallback: string;
}) {
  const { t } = useProduct();
  return (
    <>
      <label className="fg">
        {t('Python file')}
        <input
          type="file"
          accept=".py,text/x-python"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (file) onChange({ name: file.name, function: code?.function ?? fallback, source: await file.text() });
          }}
        />
      </label>
      {code && (
        <p className="hint">
          {code.name} · {code.source.length} B
        </p>
      )}
      <label className="fg">
        {t('Function name')}
        <input
          className="inp"
          value={code?.function ?? fallback}
          onChange={(e) => onChange({ name: code?.name ?? '', source: code?.source ?? '', function: e.target.value })}
        />
      </label>
    </>
  );
}
export function V3Fields({
  value,
  onChange,
  alpha,
}: {
  value: V3Settings;
  onChange: (value: V3Settings) => void;
  alpha: number;
}) {
  const { t } = useProduct();
  const set = (patch: Partial<V3Settings>) => onChange({ ...value, ...patch });
  const code = (role: PythonCode['role']) => (value.pythonCode ?? []).find((c) => c.role === role);
  const setCode = (role: PythonCode['role'], entry: Omit<PythonCode, 'role'> | null, patch: Partial<V3Settings> = {}) =>
    set({
      ...patch,
      pythonCode: [...(value.pythonCode ?? []).filter((c) => c.role !== role), ...(entry ? [{ ...entry, role }] : [])],
    });
  const space = value.weightSpace;
  const scorer = value.scorer;
  const scorerConfig = (patch: Record<string, unknown>) => {
    if (scorer.kind === 'declarative') set({ scorer: { ...scorer, config: { ...scorer.config, ...patch } } });
  };
  return (
    <div className="setup-grid">
      <label className="fg">
        {t('Weight space')}
        <select
          className="sel"
          value={space.kind}
          onChange={(e) => {
            const kind = e.target.value;
            const weightSpace: WeightSpace =
              kind === 'subset'
                ? { kind, include: [] }
                : kind === 'lora'
                  ? { kind, rank: 8, alpha: 16, targetModules: ['q_proj', 'v_proj'] }
                  : { kind: 'full' };
            set({ weightSpace });
          }}
        >
          <option value="full">{t('All parameters')}</option>
          <option value="subset">{t('Selected parameters')}</option>
          <option value="lora">{t('LoRA adapters')}</option>
        </select>
      </label>
      {space.kind === 'subset' && (
        <label className="fg">
          {t('Parameter patterns (one per line)')}
          <textarea
            className="inp"
            required
            value={space.include.join('\n')}
            onChange={(e) => set({ weightSpace: { ...space, include: e.target.value.split('\n') } })}
          />
        </label>
      )}
      {space.kind === 'lora' && (
        <>
          <label className="fg">
            {t('LoRA rank')}
            <input
              className="inp"
              type="number"
              required
              min={1}
              max={1024}
              value={space.rank}
              onChange={(e) => set({ weightSpace: { ...space, rank: Number(e.target.value) } })}
            />
          </label>
          <label className="fg">
            {t('LoRA alpha')}
            <input
              className="inp"
              type="number"
              required
              min={0.000001}
              step="any"
              value={space.alpha}
              onChange={(e) => set({ weightSpace: { ...space, alpha: Number(e.target.value) } })}
            />
          </label>
          <label className="fg">
            {t('Target modules (comma separated)')}
            <input
              className="inp"
              required
              value={space.targetModules.join(',')}
              onChange={(e) =>
                set({ weightSpace: { ...space, targetModules: e.target.value.split(',').map((s) => s.trim()) } })
              }
            />
          </label>
        </>
      )}
      <label className="fg">
        {t('Antithetic sampling')}
        <input type="checkbox" checked={value.antithetic} onChange={(e) => set({ antithetic: e.target.checked })} />
      </label>
      <label className="fg">
        {t('Coefficient rule')}
        <select
          className="sel"
          value={value.coefficientRule.startsWith('python@1') ? 'python@1' : value.coefficientRule}
          onChange={(e) =>
            e.target.value === 'python@1'
              ? set({ coefficientRule: 'python@1' })
              : setCode('coefficients', null, { coefficientRule: e.target.value })
          }
        >
          {RULES.map(([rule, label]) => (
            <option key={rule} value={rule}>
              {t(label)} · {rule}
            </option>
          ))}
        </select>
      </label>
      {value.coefficientRule.startsWith('python@1') && (
        <CodeUpload
          code={code('coefficients')}
          fallback="coefficients"
          onChange={(entry) => setCode('coefficients', entry)}
        />
      )}
      <label className="fg">
        {t('Batch sampler')}
        <select className="sel" value={value.sampler} onChange={(e) => set({ sampler: e.target.value })}>
          <option value="sha256-python-random-sample-v1">{t('Independent sample per generation')}</option>
          <option value="epoch-shuffle@1">{t('Shuffled epochs (every row once per epoch)')}</option>
        </select>
      </label>
      <div className="fg">
        <label htmlFor="candidate-seed-group">{t('Candidate seed group')}</label>
        <input
          id="candidate-seed-group"
          aria-describedby="candidate-seed-group-help"
          className="inp"
          value={value.candidateSeedNamespace ?? ''}
          maxLength={128}
          pattern="[A-Za-z0-9][A-Za-z0-9_.:\-]*"
          onChange={(e) => set({ candidateSeedNamespace: e.target.value || null })}
        />
        <small id="candidate-seed-group-help">
          {t('Use the same value to compare runs with the same candidate seeds. Leave blank for fresh seeds.')}
        </small>
      </div>
      <label className="fg">
        {t('Alpha schedule')}
        <select
          className="sel"
          value={value.alphaSchedule}
          onChange={(e) => onChange(withAlphaSchedule(value, e.target.value, alpha))}
        >
          <option value="constant">constant</option>
          <option value="cosine">cosine</option>
          <option value="linear">linear</option>
        </select>
      </label>
      {value.alphaSchedule !== 'constant' && (
        <label className="fg">
          {t('Minimum alpha')}
          <input
            className="inp"
            type="number"
            required
            min={0.0000001}
            max={1}
            step="any"
            value={value.alphaMinimum ?? ''}
            onChange={(e) => set({ alphaMinimum: e.target.value === '' ? null : Number(e.target.value) })}
          />
        </label>
      )}
      <label className="fg">
        {t('Momentum')}
        <input
          type="checkbox"
          checked={value.momentumBeta !== null}
          onChange={(e) => set({ momentumBeta: e.target.checked ? 0.875 : null })}
        />
      </label>
      {value.momentumBeta !== null && (
        <>
          <label className="fg">
            {t('Momentum beta')}
            <select
              className="sel"
              value={value.momentumBeta}
              onChange={(e) => set({ momentumBeta: Number(e.target.value) })}
            >
              {[0.5, 0.75, 0.875, 0.9375].map((beta) => (
                <option key={beta} value={beta}>
                  {beta}
                </option>
              ))}
            </select>
          </label>
          <label className="fg">
            {t('Momentum window (generations)')}
            <input
              className="inp"
              type="number"
              required
              min={2}
              max={8}
              value={value.momentumWindow}
              onChange={(e) => set({ momentumWindow: Number(e.target.value) })}
            />
          </label>
        </>
      )}
      <label className="fg">
        {t('Prompts per generation call')}
        <select
          className="sel"
          value={value.evalChunk ?? 16}
          onChange={(e) => set({ evalChunk: Number(e.target.value) === 16 ? null : Number(e.target.value) })}
        >
          {[16, 32, 64].map((chunk) => (
            <option key={chunk} value={chunk}>
              {chunk}
            </option>
          ))}
        </select>
      </label>
      <label className="fg">
        {t('Scorer')}
        <select
          className="sel"
          value={scorer.kind === 'python' ? PYTHON : scorer.name}
          onChange={(e) => {
            const name = e.target.value;
            if (name === PYTHON) {
              set({ scorer: { kind: 'python', name: 'python-reward', version: 1, codeSha256: null, config: {} } });
              return;
            }
            const config: Record<string, unknown> =
              name === 'exact-string'
                ? { answerField: 'answer', strip: true, casefold: false }
                : name === 'regex'
                  ? { answerField: 'answer', pattern: '(.*)' }
                  : name === 'choice-letter'
                    ? { answerField: 'answer' }
                    : name === 'countdown'
                      ? { numbersField: 'nums', targetField: 'target' }
                      : name === 'boxed-number'
                        ? { answerField: 'answer', formatReward: 0 }
                        : {};
            setCode('scorer', null, {
              scorer: { kind: 'declarative', name, version: 1, codeSha256: null, config },
            });
          }}
        >
          {SCORERS.map((name) => (
            <option key={name} value={name}>
              {name}@1
            </option>
          ))}
          <option value={PYTHON}>{t('Your Python scorer (upload a .py file)')}</option>
        </select>
      </label>
      {scorer.kind === 'python' && (
        <>
          <CodeUpload code={code('scorer')} fallback="reward" onChange={(entry) => setCode('scorer', entry)} />
          <p className="hint">
            {t(
              'Your code runs on the coordinator device with the permissions of its user, in a child process with a time limit. Workers never run it. It receives (texts, rows) and returns one number per text.',
            )}
          </p>
        </>
      )}
      {'answerField' in scorer.config && (
        <label className="fg">
          {t('Scorer answer field')}
          <input
            className="inp"
            required
            value={String(scorer.config.answerField)}
            onChange={(e) => scorerConfig({ answerField: e.target.value })}
          />
        </label>
      )}
      {'formatReward' in scorer.config && (
        <label className="fg">
          {t('Format reward')}
          <input
            className="inp"
            type="number"
            min={0}
            max={0.99}
            step={0.01}
            value={Number(scorer.config.formatReward)}
            onChange={(e) => scorerConfig({ formatReward: Number(e.target.value) })}
          />
          <span className="hint">{t('Reward for a well-formed boxed number with the wrong value.')}</span>
        </label>
      )}
      {'numbersField' in scorer.config && (
        <>
          <label className="fg">
            {t('Scorer numbers field')}
            <input
              className="inp"
              required
              value={String(scorer.config.numbersField)}
              onChange={(e) => scorerConfig({ numbersField: e.target.value })}
            />
          </label>
          <label className="fg">
            {t('Scorer target field')}
            <input
              className="inp"
              required
              value={String(scorer.config.targetField)}
              onChange={(e) => scorerConfig({ targetField: e.target.value })}
            />
          </label>
        </>
      )}
      {'pattern' in scorer.config && (
        <label className="fg">
          {t('Regex pattern')}
          <input
            className="inp"
            required
            maxLength={500}
            value={String(scorer.config.pattern)}
            onChange={(e) => scorerConfig({ pattern: e.target.value })}
          />
        </label>
      )}
      {'strip' in scorer.config && (
        <label className="fg">
          {t('Trim whitespace')}
          <input
            type="checkbox"
            checked={Boolean(scorer.config.strip)}
            onChange={(e) => scorerConfig({ strip: e.target.checked })}
          />
        </label>
      )}
      {'casefold' in scorer.config && (
        <label className="fg">
          {t('Ignore letter case')}
          <input
            type="checkbox"
            checked={Boolean(scorer.config.casefold)}
            onChange={(e) => scorerConfig({ casefold: e.target.checked })}
          />
        </label>
      )}
      <label className="fg">
        {t('Prompt format')}
        <select
          className="sel"
          value={value.promptFormat ?? 'chat'}
          onChange={(e) =>
            set(e.target.value === 'raw' ? { promptFormat: 'raw', systemPrompt: null } : { promptFormat: null })
          }
        >
          <option value="chat">{t('Chat template')}</option>
          <option value="raw">{t('Raw dataset prompts')}</option>
        </select>
        {value.promptFormat === 'raw' && (
          <span className="hint">{t('Raw prompts are sent exactly as stored in the dataset.')}</span>
        )}
      </label>
      <label className="fg">
        {t('Use a system prompt')}
        <input
          type="checkbox"
          disabled={value.promptFormat === 'raw'}
          checked={value.systemPrompt !== null}
          onChange={(e) => set({ systemPrompt: e.target.checked ? '' : null })}
        />
      </label>
      {value.systemPrompt !== null && (
        <label className="fg">
          {t('System prompt')}
          <textarea
            className="inp"
            required
            maxLength={4000}
            value={value.systemPrompt}
            onChange={(e) => set({ systemPrompt: e.target.value })}
          />
        </label>
      )}
    </div>
  );
}
