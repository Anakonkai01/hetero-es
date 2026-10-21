import { useProduct } from '@heteroes/product-ui';
import { useInstallerManifest } from '../../hooks/useInstallerManifest';
import { LinuxWorkerCommand } from './LinuxWorkerCommand';

export function InstallerDownloads() {
  const { t } = useProduct();
  const manifest = useInstallerManifest();
  const apps = [
    {
      name: 'Worker',
      items: manifest.data?.installers ?? [],
      description: 'Connect your GPU and choose when to contribute.',
    },
    {
      name: 'Lab Server',
      items: manifest.data?.serverInstallers ?? [],
      description: 'Host the dashboard, queue and checkpoint service on a CPU computer.',
    },
  ];
  return (
    <section className="landing-downloads" id="downloads">
      <div className="section-title">
        <div>
          <span className="eyebrow">{t('Desktop apps')}</span>
          <h2>{t('Bring your computers into the lab.')}</h2>
          <p>{t('Use Worker on GPU computers and Lab Server on the computer hosting your lab.')}</p>
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
      ) : (
        <div className="download-cards">
          {apps.map(({ name, items, description }) => (
            <article key={name}>
              <h3>HeteroES {name}</h3>
              <p>{t(description)}</p>
              <div className="acts">
                {items
                  .filter((item) => item.platform === 'windows')
                  .map((item) => (
                    <a className="btn" href={item.url} download={item.name} key={item.platform}>
                      Windows <span aria-hidden="true">↓</span>
                    </a>
                  ))}
              </div>
              {!items.length && <p className="hint">{t('No installer available')}</p>}
              {name === 'Lab Server' && (
                <p className="hint">{t('On Linux the lab runs as a service from the command line (see the handbook).')}</p>
              )}
              {name === 'Worker' && <LinuxWorkerCommand manifest={manifest.data} />}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
