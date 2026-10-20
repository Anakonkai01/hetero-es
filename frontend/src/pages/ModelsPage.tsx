import { Status, useProduct } from '@heteroes/product-ui';
import { Link } from 'react-router';
import { QueryState } from '../components/common/QueryState';
import { StudyAssets } from '../components/experiments/StudyAssets';
import { ModelQualification } from '../components/experiments/ModelQualification';
import { PageHeader } from '../components/ui/PageHeader';
import { useModels } from '../hooks/useAccess';
export function ModelsPage() {
  const { t } = useProduct();
  const models = useModels();
  return (
    <>
      <PageHeader title={t('Models')} description={t('Pinned model references used by the current runtime.')} />
      <QueryState
        isPending={models.isPending}
        isError={models.isError}
        hasData={Boolean(models.data)}
        title={t('Model capabilities unavailable')}
      >
        <div className="resource-grid">
          {models.data?.map((model) => (
            <section className="card model-card" key={model.modelArtifactId} data-model-id={model.modelArtifactId}>
              <Status value="Pinned" />
              <h2>{model.name}</h2>
              <p className="hint">{model.reference ?? model.name}</p>
              <dl className="model-identity">
                <dt>{t('Pinned revision')}</dt>
                <dd className="mono">{model.revision}</dd>
              </dl>
              <p className="info-caption">{t('Workers use this fixed model revision for reproducible evaluations.')}</p>
              <div className="acts">
                <Link className="btn pri" to="/experiments/new">
                  {t('Create experiment')} →
                </Link>
              </div>
              {model.recipeVersion === 3 && model.manifestHash && (
                <ModelQualification assetId={model.modelArtifactId} manifestHash={model.manifestHash} />
              )}
            </section>
          ))}
        </div>
        <StudyAssets />
      </QueryState>
    </>
  );
}
