import { CopyValue, useProduct } from '@heteroes/product-ui';
import type { Manifest } from '../../hooks/useInstallerManifest';
import { linuxInstallCommand } from '../../lib/linuxInstall';

/** The one-line Worker install for Linux (the only way on Linux: no desktop app); nothing when this build has none. */
export function LinuxWorkerCommand({ manifest }: { manifest: Manifest | undefined }) {
  const { t } = useProduct();
  const url = manifest?.linuxWorker?.installer.url;
  const command = url ? linuxInstallCommand(url, window.location.origin) : null;
  if (!command) return null;
  return (
    <div className="linux-worker" data-linux-worker>
      <b>{t('Linux (command line)')}</b>
      <p className="hint">
        {t('Paste this line into a terminal. It needs no administrator password and checks every download.')}
      </p>
      <CopyValue value={command} label="Copy command" />
      <details className="install-details">
        <summary>{t('Detailed instructions')}</summary>
        <p className="hint">
          {t(
            'It then checks the GPU, asks for a pairing code from Workers → Add a GPU computer and keeps the machine online in the background. Afterwards:',
          )}
        </p>
        <pre className="mono">{`heteroes-worker status\nheteroes-worker on | off\nheteroes-worker doctor`}</pre>
      </details>
    </div>
  );
}
