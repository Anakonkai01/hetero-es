import { useProduct } from '@heteroes/product-ui';
import type { V3Settings, WeightSpace } from '../../types/experiment';

const SCORERS = [
  'exact-string',
  'choice-letter',
  'regex',
  'answer-line-last-number',
  'last-integer',
  'answer-line-integer',
  'countdown',
];
// coefficient rules a shared lab runs (a python rule needs a self-hosted coordinator)
const RULES: [string, string][] = [
  ['zscore@1', 'Z-score of the rewards'],
  ['centered-rank@1', 'Centered ranks of the rewards'],
];
export function V3Fields({ value, onChange }: { value: V3Settings; onChange: (value: V3Settings) => void }) {
  const { t } = useProduct();
  const set = (patch: Partial<V3Settings>) => onChange({ ...value, ...patch });
  const space = value.weightSpace;
  const scorer = value.scorer;
  const scorerConfig = (patch: Record<string, unknown>) =>
    set({ scorer: { ...scorer, config: { ...scorer.config, ...patch } } });
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
          value={value.coefficientRule}
          onChange={(e) => set({ coefficientRule: e.target.value })}
        >
          {RULES.map(([rule, label]) => (
            <option key={rule} value={rule}>
              {t(label)} · {rule}
            </option>
          ))}
        </select>
      </label>
      <label className="fg">
        {t('Alpha schedule')}
        <select className="sel" value={value.alphaSchedule} onChange={(e) => set({ alphaSchedule: e.target.value })}>
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
        {t('Declarative scorer')}
        <select
          className="sel"
          value={scorer.name}
          onChange={(e) => {
            const name = e.target.value;
            const config: Record<string, unknown> =
              name === 'exact-string'
                ? { answerField: 'answer', strip: true, casefold: false }
                : name === 'regex'
                  ? { answerField: 'answer', pattern: '(.*)' }
                  : name === 'choice-letter'
                    ? { answerField: 'answer' }
                    : name === 'countdown'
                      ? { numbersField: 'nums', targetField: 'target' }
                      : {};
            set({ scorer: { ...scorer, name, config } });
          }}
        >
          {SCORERS.map((name) => (
            <option key={name} value={name}>
              {name}@1
            </option>
          ))}
        </select>
      </label>
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
        {t('Use a system prompt')}
        <input
          type="checkbox"
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
