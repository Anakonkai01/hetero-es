import { useProduct } from '@heteroes/product-ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { apiGet, apiPost } from '../../api/client';
import { useScopeKey } from '../../app/session';

export interface StudyDataset {
  recipeVersion?: number;
  columns?: string[];
  datasetId: string;
  name: string;
  counts: { train: number; validation: number; test: number };
  identity: { contentHash: string };
  splitSeed: number;
  splitMode: string;
}
export interface StudyModel {
  modelArtifactId: string;
  name: string;
  reference: string;
  revision: string;
  status: string;
  manifest?: Record<string, unknown>;
}
type SourceFile = { format: string; content: string };

export function StudyAssets() {
  const { t } = useProduct();
  const cache = useQueryClient();
  const scope = useScopeKey();
  const health = useQuery({
    queryKey: ['study-health'],
    queryFn: () => apiGet<{ privateLabUrl?: string }>('/api/v1/health'),
  });
  const data = useQuery({
    queryKey: ['study-datasets', ...scope],
    queryFn: () => apiGet<StudyDataset[]>('/api/v1/datasets'),
    enabled: scope.every(Boolean),
  });
  const [recipeVersion, setRecipeVersion] = useState(2);
  const [name, setName] = useState('');
  const [mode, setMode] = useState('all');
  const [prompt, setPrompt] = useState('prompt');
  const [answer, setAnswer] = useState('answer');
  const [adapter, setAdapter] = useState('exact-number-v1');
  const [files, setFiles] = useState<Record<string, SourceFile>>({});
  const [manifest, setManifest] = useState<Record<string, unknown> | null>(null);
  const [modelName, setModelName] = useState('');
  const [source, setSource] = useState('REFERENCE');
  const [weightFiles, setWeightFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const publicEntry = location.hostname.endsWith('.trycloudflare.com');
  const perform = async (task: () => Promise<void>) => {
    setBusy(true);
    setMessage('');
    try {
      await task();
      await cache.invalidateQueries();
      setMessage(t('Saved and verified.'));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card">
      <div className="ch">
        <h2>{t('Models and datasets')}</h2>
      </div>
      <div className="cb demo-form">
        {message && (
          <p className="note" role="status">
            {message}
          </p>
        )}
        <label className="fg">
          {t('Asset recipe')}
          <select className="sel" value={recipeVersion} onChange={(e) => setRecipeVersion(Number(e.target.value))}>
            <option value={2}>{t('Math dataset · Recipe v2')}</option>
            <option value={3}>{t('Custom experiment · Recipe v3')}</option>
          </select>
        </label>
        {publicEntry ? (
          <p className="note">
            {t('Connect to the lab LAN or Tailscale to import datasets and model files.')}{' '}
            {health.data?.privateLabUrl && (
              <a href={health.data.privateLabUrl} className="link">
                {t('Open private lab')}
              </a>
            )}
          </p>
        ) : (
          <>
            <details className="advanced-panel">
              <summary>{t('Import dataset')}</summary>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void perform(async () => {
                    await apiPost('/api/v1/datasets/import', {
                      name,
                      files,
                      recipeVersion,
                      mapping: recipeVersion === 3 ? { prompt } : { prompt, answer },
                      adapter,
                      splitSeed: 42,
                    });
                  });
                }}
              >
                <label className="fg">
                  {t('Dataset name')}
                  <input
                    className="inp"
                    required
                    maxLength={100}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </label>
                <label className="fg">
                  {t('Dataset splits')}
                  <select
                    className="sel"
                    value={mode}
                    onChange={(e) => {
                      setMode(e.target.value);
                      setFiles({});
                    }}
                  >
                    <option value="all">{t('One file · seeded 80/10/10')}</option>
                    <option value="split">{t('Train, validation and test files')}</option>
                  </select>
                </label>
                <div className="setup-grid">
                  <label className="fg">
                    {t('Prompt field')}
                    <input className="inp" required value={prompt} onChange={(e) => setPrompt(e.target.value)} />
                  </label>
                  {recipeVersion === 2 && (
                    <label className="fg">
                      {t('Answer field')}
                      <input className="inp" required value={answer} onChange={(e) => setAnswer(e.target.value)} />
                    </label>
                  )}
                </div>
                {recipeVersion === 2 && (
                  <label className="fg">
                    {t('Answer format')}
                    <select className="sel" value={adapter} onChange={(e) => setAdapter(e.target.value)}>
                      <option value="exact-number-v1">{t('Exact number')}</option>
                      <option value="gsm8k-v1">GSM8K · ####</option>
                    </select>
                  </label>
                )}
                {(mode === 'all' ? ['all'] : ['train', 'validation', 'test']).map((split) => (
                  <label className="fg" key={split}>
                    {split}
                    <input
                      key={mode + split}
                      type="file"
                      required
                      accept=".json,.jsonl,.csv"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (!file) return;
                        if (file.size > 3_000_000) {
                          setMessage(t('Dataset file exceeds 3 MB.'));
                          return;
                        }
                        void file
                          .text()
                          .then((content) =>
                            setFiles((previous) => ({
                              ...previous,
                              [split]: { content, format: file.name.split('.').at(-1) ?? '' },
                            })),
                          )
                          .catch(() => setMessage(t('Cannot read file.')));
                      }}
                    />
                  </label>
                ))}
                <p className="hint">
                  {t(
                    'Split seed: 42. Duplicate prompts are rejected. Test examples stay out of training and checkpoint selection.',
                  )}
                </p>
                <button className="btn" disabled={busy || Object.keys(files).length !== (mode === 'all' ? 1 : 3)}>
                  {t('Import dataset')}
                </button>
              </form>
            </details>
            <details className="advanced-panel">
              <summary>{t('Register pinned model')}</summary>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void perform(async () => {
                    if (!manifest) throw Error(t('Select a pinned file manifest.'));
                    const asset = await apiPost<{ id: string }>('/api/v1/models/register', {
                      name: modelName,
                      manifest,
                      recipeVersion,
                      source,
                    });
                    if (source === 'UPLOAD') {
                      const named = Object.fromEntries(
                        weightFiles.map((file) => [
                          file.webkitRelativePath ? file.webkitRelativePath.split('/').slice(1).join('/') : file.name,
                          file,
                        ]),
                      );
                      const expected = manifest.files as Record<string, string>;
                      const sizes = Object.fromEntries(
                        Object.keys(expected).map((key) => {
                          if (!named[key]) throw Error(t('Missing pinned model file: ') + key);
                          return [key, named[key].size];
                        }),
                      );
                      const plans = await apiPost<Record<string, { url: string; headers: Record<string, string> }>>(
                        '/api/v1/models/' + asset.id + '/upload-plan',
                        sizes,
                      );
                      for (const [key, plan] of Object.entries(plans)) {
                        const response = await fetch(plan.url, { method: 'PUT', body: named[key] });
                        if (!response.ok) throw Error(t('Model upload failed: ') + key);
                      }
                      await apiPost('/api/v1/models/' + asset.id + '/publish');
                    }
                  });
                }}
              >
                <label className="fg">
                  {t('Model name')}
                  <input
                    className="inp"
                    required
                    maxLength={100}
                    value={modelName}
                    onChange={(e) => setModelName(e.target.value)}
                  />
                </label>
                <label className="fg">
                  {t('Pinned file manifest')}
                  <input
                    type="file"
                    accept=".json"
                    required
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (!file || file.size > 100000) return;
                      void file
                        .text()
                        .then((text) => setManifest(JSON.parse(text) as Record<string, unknown>))
                        .catch(() => setMessage(t('Invalid model manifest.')));
                    }}
                  />
                </label>
                <label className="fg">
                  {t('Model source')}
                  <select className="sel" value={source} onChange={(e) => setSource(e.target.value)}>
                    <option value="REFERENCE">{t('Pinned Hugging Face reference')}</option>
                    <option value="UPLOAD">{t('Upload safetensors and tokenizer files')}</option>
                  </select>
                </label>
                {source === 'UPLOAD' && (
                  <label className="fg">
                    {t('Model files')}
                    <input
                      type="file"
                      multiple
                      required
                      onChange={(e) => setWeightFiles(Array.from(e.target.files ?? []))}
                    />
                  </label>
                )}
                <p className="hint">
                  {t(
                    'The manifest pins commit revisions and every file checksum. Every selected GPU must qualify for the model before training.',
                  )}
                </p>
                <button className="btn" disabled={busy || !manifest}>
                  {t('Register model')}
                </button>
              </form>
            </details>
          </>
        )}
        <h3>{t('Frozen datasets')}</h3>
        {data.data?.map((item) => (
          <div className="demo-item" key={item.datasetId}>
            <b>{item.name}</b>
            <span>
              {item.counts.train} / {item.counts.validation} / {item.counts.test} · {item.splitMode} ·{' '}
              {item.identity.contentHash.slice(0, 12)}
            </span>
          </div>
        ))}
        {data.error && <p role="alert">{data.error.message}</p>}
      </div>
    </section>
  );
}
