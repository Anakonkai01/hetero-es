import { CopyValue, useProduct } from '@heteroes/product-ui';
import type { Manifest } from '../../hooks/useInstallerManifest';
import { linuxInstallCommand } from '../../lib/linuxInstall';

/** The one-line Worker install for Linux computers and WSL without a desktop; nothing when this build has none. */
export function LinuxWorkerCommand({ manifest }: { manifest: Manifest | undefined }) {
  const { t } = useProduct();
  const url = manifest?.linuxWorker?.installer.url;
  const command = url ? linuxInstallCommand(url, window.location.origin) : null;
  if (!command) return null;
  return (
    <div className="linux-worker" data-linux-worker>
      <b>{t('Linux or WSL without a desktop')}</b>
      <p className="hint">
        {t('Paste this line into a terminal. It needs no administrator password and checks every download.')}
      </p>
      <CopyValue value={command} label="Copy command" />
      <p className="hint">
        {t('Then check the GPU, pair it with a code from Workers → Add a GPU computer, and keep it online:')}
      </p>
      <pre className="mono">
        {`heteroes-worker selftest\nheteroes-worker join ${window.location.origin}\nheteroes-worker run`}
      </pre>
    </div>
  );
}
