import { useProduct } from '@heteroes/product-ui';
import { useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { ExperimentConfiguration } from '../components/experiments/ExperimentConfiguration';
import { TemplatePicker } from '../components/experiments/TemplatePicker';
import { PageHeader } from '../components/ui/PageHeader';
import { useCreateExperiment } from '../hooks/useExperimentMutations';
import { wizardStart, type Template } from '../lib/templates';
import type { Experiment } from '../types/experiment';
export function ExperimentCreatePage() {
  const { t } = useProduct();
  const create = useCreateExperiment();
  const navigate = useNavigate();
  const clone = (
    useLocation().state as {
      clone?: Experiment;
    } | null
  )?.clone;
  const [source, setSource] = useState(clone ? 'clone' : '');
  const [template, setTemplate] = useState<Template>();
  const initial = useMemo(
    () => (source === 'clone' ? wizardStart({ clone }) : template ? wizardStart({ template }) : undefined),
    [source, clone, template],
  );
  return (
    <>
      <PageHeader
        title={t('Create experiment')}
        description={t('Choose a built-in workload, ES configuration and workers from the shared pool.')}
      />
      {
        <section className="card">
          <div className="cb">
            <TemplatePicker
              value={source}
              cloneName={clone?.name}
              onChange={(id, picked) => {
                setSource(id);
                setTemplate(picked);
              }}
            />
          </div>
        </section>
      }
      <section className="card">
        <ExperimentConfiguration
          key={source || 'empty'}
          initial={initial as Experiment | undefined}
          pending={create.isPending}
          onSave={async (configuration) => {
            const e = await create.mutateAsync(configuration);
            navigate(`/experiments/${e.experimentId}`);
          }}
        />
      </section>
    </>
  );
}
