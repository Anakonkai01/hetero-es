import { PreferencesControl, ProductMark, useProduct } from '@heteroes/product-ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { apiGet } from '../api/client';
import { useSession } from '../app/session';
import { InstallerDownloads } from '../components/common/InstallerDownloads';
import { DemoReplay } from '../components/live/DemoReplay';
import { ChipIcon, DashboardIcon, FileIcon, FlaskIcon } from '../components/ui/Icons';

export function HomePage() {
  const { t } = useProduct();
  const { session } = useSession();
  const health = useQuery({
    queryKey: ['control-health'],
    queryFn: () => apiGet<{ ok: boolean }>('/api/v1/health'),
    refetchInterval: 15000,
    retry: 1,
  });
  const features = [
    {
      icon: <ChipIcon />,
      title: 'Your GPUs. One shared lab.',
      text: 'Connect GPU computers, check compatibility and choose when to contribute.',
    },
    {
      icon: <FlaskIcon />,
      title: 'Follow every generation.',
      text: 'Inspect candidates, seeds, rewards and accepted results throughout an experiment.',
    },
    {
      icon: <FileIcon />,
      title: 'Keep your progress.',
      text: 'Track saved checkpoints and recovery status alongside the experiment that produced them.',
    },
  ];
  return (
    <div className="public-site">
      <header className="public-header">
        <Link className="public-brand" to="/">
          <ProductMark />
          Hetero<span>ES</span>
        </Link>
        <nav aria-label={t('Primary navigation')}>
          <Link to="/explain">{t('How it works')}</Link>
          <a href="#capabilities">{t('Capabilities')}</a>
        </nav>
        <div className="acts">
          <PreferencesControl />
          <Link className="btn pri" to={session ? '/dashboard' : '/login'}>
            {t(session ? 'Open dashboard' : 'Sign in')} <span aria-hidden="true">↗</span>
          </Link>
        </div>
      </header>
      <main id="main-content">
        <section className="landing-hero">
          <div className="hero-copy">
            <span className="landing-kicker">
              <span className="live-dot" /> {t('A local lab for distributed ES')}
            </span>
            <h1>
              {t('A shared space.')}
              <br />
              <span>{t('For your next experiment.')}</span>
            </h1>
            <p>
              {t(
                'Bring your GPU computers together to explore LLM fine-tuning with Evolution Strategies. Manage resources, follow each generation and keep your results in one place.',
              )}
            </p>
            <div className="hero-actions">
              <Link className="btn pri" to={session ? '/dashboard' : '/login'}>
                {t(session ? 'Open dashboard' : 'Enter your lab')} <span aria-hidden="true">→</span>
              </Link>
              <Link className="btn" to="/explain">
                {t('Explore the workflow')}
              </Link>
            </div>
            <div className="hero-caption">
              <span className={health.isError ? 'live-dot offline' : 'live-dot'} />
              {t(
                health.isPending
                  ? 'Connecting to your lab…'
                  : health.isError
                    ? 'Lab connection unavailable'
                    : health.data?.ok
                      ? 'Lab API is reachable'
                      : 'Lab status unavailable',
              )}
              <span>·</span>
              {t('Any network')}
            </div>
          </div>
          <DemoReplay
            fallback={
              <div className="lab-map" aria-label={t('Distributed experiment workflow')}>
                <div className="map-header">
                  <span>
                    <DashboardIcon />
                    {t('Inside your lab')}
                  </span>
                  <span className="map-label">HETEROES</span>
                </div>
                <div className="map-coordinator">
                  <div className="map-icon">
                    <FlaskIcon />
                  </div>
                  <div>
                    <small>{t('Orchestration')}</small>
                    <strong>{t('Queue & coordinator')}</strong>
                    <span>{t('Assign · evaluate · aggregate')}</span>
                  </div>
                </div>
                <div className="map-connectors" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </div>
                <div className="map-workers">
                  {['GPU computer A', 'GPU computer B', 'GPU computer C'].map((name, i) => (
                    <div key={name}>
                      <ChipIcon />
                      <b>{t(name)}</b>
                      <small>{t(i === 1 ? 'Candidate evaluation' : 'Owner-controlled contribution')}</small>
                    </div>
                  ))}
                </div>
                <div className="map-result">
                  <FileIcon />
                  <div>
                    <strong>{t('Checkpoint & experiment history')}</strong>
                    <small>{t('Generations · candidates · seeds · rewards')}</small>
                  </div>
                  <span aria-hidden="true">↗</span>
                </div>
                <p className="map-footnote">{t('Workflow illustration. Live devices appear after you sign in.')}</p>
              </div>
            }
          />
        </section>
        <section className="landing-features" id="capabilities">
          {features.map((feature) => (
            <article key={feature.title}>
              <span className="feature-icon">{feature.icon}</span>
              <h2>{t(feature.title)}</h2>
              <p>{t(feature.text)}</p>
            </article>
          ))}
        </section>
        <section className="landing-workflow" id="how-it-works">
          <div>
            <span className="eyebrow">{t('From setup to results')}</span>
            <h2>{t('One workflow, across your computers.')}</h2>
            <p>{t('The web manages your lab. Worker apps connect your GPUs. Lab Server hosts the control service.')}</p>
          </div>
          <ol>
            {[
              ['01', 'Connect your computers', 'Install Worker, verify your GPU and pair it with your lab.'],
              ['02', 'Prepare an experiment', 'Choose a workload, generation count and GPU resources.'],
              ['03', 'Follow the results', 'Watch candidates, compare rewards and inspect saved checkpoints.'],
            ].map(([n, title, text]) => (
              <li key={n}>
                <span>{n}</span>
                <div>
                  <h3>{t(title)}</h3>
                  <p>{t(text)}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
        <InstallerDownloads />
      </main>
      <footer className="public-footer">
        <span>
          HeteroES <span className="mut">· {t('Research together')}</span>
        </span>
        <Link to={session ? '/workspace' : '/register'}>{t(session ? 'Your workspaces' : 'Create an account')} →</Link>
      </footer>
    </div>
  );
}
