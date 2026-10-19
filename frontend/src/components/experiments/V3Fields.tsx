import { useProduct } from '@heteroes/product-ui';
import type { V3Settings, WeightSpace } from '../../types/experiment';

const SCORERS = [
  'exact-string',
  'choice-letter',
  'regex',
  'answer-line-last-number',
  'last-integer',
  'answer-line-integer',
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
          <option value="zscore@1">{value.coefficientRule}</option>
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
