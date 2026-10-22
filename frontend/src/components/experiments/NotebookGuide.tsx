import { useProduct } from '@heteroes/product-ui';

// A notebook is the way to create an experiment (owner 2026-10-22): the model and rows come from the researcher's own
// code, and the reward and sampler are Python functions. The text is code: it is the same in both languages.
const ORIGIN = typeof window === 'undefined' ? 'https://lab.heteroes.site' : window.location.origin;
// the lab serves the SDK wheel of its own release beside the example notebook
const INSTALL = `pip install "${ORIGIN}/notebooks/heteroes-0.0.1-py3-none-any.whl" huggingface_hub`;
const EXAMPLE = `from heteroes.sdk import ESConfig, ESTrainer
from heteroes.sdk_lab import Dataset, Lab, Model

lab = Lab.connect("${ORIGIN}")
model = Model.from_hf("Qwen/Qwen2.5-0.5B-Instruct")
data = Dataset.from_rows(train=train_rows, validation=val_rows, test=test_rows)

def reward(completions, rows):
    import re
    found = [re.findall(r"-?\\d+", text) for text in completions]
    return [float(bool(f) and f[-1] == row["answer"]) for f, row in zip(found, rows)]

hint = lab.suggest(model, data, max_new_tokens=256)
args = ESConfig(model=model, dataset=data, population=32, generations=50,
                batch_size=hint.batch_size, eval_chunk=hint.eval_chunk, eval_chunks=hint.eval_chunks)
run = ESTrainer(args, reward_func=reward).submit(lab, coordinator="my-gpu", workers=["my-gpu", "friend-gpu"])
run.watch()`;

export function NotebookGuide() {
  const { t } = useProduct();
  return (
    <section className="card">
      <div className="ch">
        <h2>{t('Create an experiment from a notebook')}</h2>
      </div>
      <div className="cb notebook-guide">
        <p>
          {t(
            'Load a model and rows with your own code, write the reward (and, if you like, the sampler) in Python, then submit. The notebook pins every input, qualifies the devices and returns a run you can watch here or in the notebook.',
          )}
        </p>
        <pre>
          <code>{EXAMPLE}</code>
        </pre>
        <div className="acts">
          <a className="btn pri" href="/notebooks/researcher.ipynb" download="researcher.ipynb">
            {t('Download the example notebook')}
          </a>
          <button type="button" className="btn" onClick={() => void navigator.clipboard?.writeText(EXAMPLE)}>
            {t('Copy the code')}
          </button>
        </div>
        <p className="hint">{t('Install the SDK where the notebook runs (Python 3.12):')}</p>
        <pre>
          <code>{INSTALL}</code>
        </pre>
      </div>
    </section>
  );
}
