import { useState } from 'react';
import { Link } from 'react-router';
import { useProduct } from '@heteroes/product-ui';
import { useInstallerManifest } from '../../hooks/useInstallerManifest';
import { LinuxWorkerCommand } from './LinuxWorkerCommand';

export function InstallerDownloads() {
  const { t } = useProduct();
  const manifest = useInstallerManifest();
  const [app, setApp] = useState<'worker' | 'server'>('worker');
  const [os, setOs] = useState<'windows' | 'linux'>(() => (/Windows/i.test(navigator.userAgent) ? 'windows' : 'linux'));
  const items = (app === 'worker' ? manifest.data?.installers : manifest.data?.serverInstallers) ?? [];
  const windows = items.find((item) => item.platform === 'windows');
  return (
    <section className="landing-downloads" id="downloads">
      <div className="section-title">
        <div>
          <span className="eyebrow">{t('Get started')}</span>
          <h2>{t('Bring your computers into the lab.')}</h2>
          <p>{t('Use Worker on GPU computers and Lab Server on the computer hosting your lab.')}</p>
        </div>
      </div>
      <div className="install-picker" role="group" aria-label={t('Choose an app')}>
        <button className="btn" aria-pressed={app === 'worker'} onClick={() => setApp('worker')}>
          {t('Connect a GPU')}
        </button>
        <button className="btn" aria-pressed={app === 'server'} onClick={() => setApp('server')}>
          {t('Host a lab')}
        </button>
      </div>
      <article className="install-card">
        <div className="install-heading">
          <div>
            <h3>HeteroES {app === 'worker' ? 'Worker' : 'Lab Server'}</h3>
            <p>
              {t(
                app === 'worker'
                  ? 'Connect your GPU and choose when to contribute.'
                  : 'Host the dashboard, queue and checkpoint service on a CPU computer.',
              )}
            </p>
          </div>
          <div className="install-picker" data-os-picker role="group" aria-label={t('Operating system')}>
            <button className="btn" aria-pressed={os === 'windows'} onClick={() => setOs('windows')}>
              Windows
            </button>
            <button className="btn" aria-pressed={os === 'linux'} onClick={() => setOs('linux')}>
              Linux
            </button>
          </div>
        </div>
        {manifest.data?.privateTransferRequired && (
          <p className="note">{t('Connect to the lab LAN or Tailscale to download installers and large files.')}</p>
        )}
        {manifest.isPending ? (
          <p role="status">{t('Loading…')}</p>
        ) : manifest.isError ? (
          <p className="hint">
            {t('App downloads are unavailable on this server. Ask your administrator for the current installer.')}
          </p>
        ) : os === 'windows' ? (
          <>
            {windows ? (
              <a className="btn pri" href={windows.url} download={windows.name}>
                {t('Download for Windows')} ↓
              </a>
            ) : (
              <p className="hint">{t('No installer available')}</p>
            )}
            <details className="install-details">
              <summary>{t('Detailed instructions')}</summary>
              <Link to="/get-started">{t('Open setup guide')}</Link>
            </details>
          </>
        ) : app === 'worker' ? (
          <>
            <LinuxWorkerCommand manifest={manifest.data} />
            {!manifest.data?.linuxWorker && <p className="hint">{t('No installer available')}</p>}
          </>
        ) : (
          <>
            <p>{t('On Linux the lab runs as a service from the command line (see the handbook).')}</p>
            <Link className="btn" to="/get-started">
              {t('Open setup guide')}
            </Link>
          </>
        )}
      </article>
    </section>
  );
}
