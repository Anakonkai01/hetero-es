import { CopyValue, useProduct } from '@heteroes/product-ui';
import { Link } from 'react-router';
import { useSession } from '../app/session';
import { LinuxWorkerCommand } from '../components/common/LinuxWorkerCommand';
import { PageHeader } from '../components/ui/PageHeader';
import { useInstallerManifest } from '../hooks/useInstallerManifest';

const ACCOUNT_STATE: Record<string, { tone: string; text: string }> = {
  PENDING: {
    tone: 'warn',
    text: 'Waiting for an administrator to approve your account. You can install the Worker app in the meantime.',
  },
  ACTIVE: { tone: 'ok', text: 'Your account is approved.' },
  REJECTED: { tone: 'err', text: 'Your account request was declined. Ask the lab administrator.' },
  SUSPENDED: { tone: 'err', text: 'Your account is suspended. Ask the lab administrator.' },
};

export function GetStartedPage() {
  const { t } = useProduct();
  const { session } = useSession();
  const manifest = useInstallerManifest();
  const state = ACCOUNT_STATE[session?.user.accountStatus ?? 'PENDING'] ?? ACCOUNT_STATE.PENDING;
  const installers = (manifest.data?.installers ?? []).filter((item) => item.platform !== 'linux-appimage');
  return (
    <>
      <PageHeader
        title={t('Get started')}
        description={t('Three steps from a new account to a GPU that helps your lab.')}
      />
      <ol className="get-started">
        <li className="card">
          <div className="ch">
            <h2>
              <span className="step-no">1</span>
              {t('Your account')}
            </h2>
            <span className={`badge ${state.tone}`}>{t(session?.user.accountStatus ?? 'PENDING')}</span>
          </div>
          <div className="cb">
            <p>
              {session?.user.displayName} · <span className="mono">{session?.user.username}</span>
            </p>
            <p className="hint">{t(state.text)}</p>
          </div>
        </li>
        <li className="card" id="downloads">
          <div className="ch">
            <h2>
              <span className="step-no">2</span>
              {t('Install the Worker app')}
            </h2>
          </div>
          <div className="cb">
            <p>{t('The Worker connects your GPU computer to this lab. It works on Windows and Linux.')}</p>
            {manifest.isPending ? (
              <p role="status">{t('Loading…')}</p>
            ) : manifest.isError || !installers.length ? (
              <p className="note warn">
                {t('App downloads are unavailable on this server. Ask your administrator for the current installer.')}
              </p>
            ) : (
              <div className="acts">
                {installers.map((item) => (
                  <a className="btn pri" href={item.url} download={item.name} key={item.platform}>
                    {t('Download for')} {item.platform === 'windows' ? 'Windows' : 'Linux'}{' '}
                    <span aria-hidden="true">↓</span>
                  </a>
                ))}
              </div>
            )}
            <p className="hint">
              {t(
                'Windows may warn that the app is from an unknown publisher because it is not signed yet. Choose More info, then Run anyway.',
              )}
            </p>
            <p className="hint">
              {t('When the app asks for the lab address, use this one (it is usually filled in already):')}
            </p>
            <CopyValue value={window.location.origin} label="Copy address" />
            <LinuxWorkerCommand manifest={manifest.data} />
          </div>
        </li>
        <li className="card">
          <div className="ch">
            <h2>
              <span className="step-no">3</span>
              {t('Pair your GPU')}
            </h2>
          </div>
          <div className="cb">
            <p>
              {t(
                'In the app, sign in with this same account, run the GPU check, then pair the device. An administrator approves it before it can receive work.',
              )}
            </p>
            <p className="hint">{t('Your GPU stays off until you choose to contribute.')}</p>
            <div className="acts">
              <Link className="btn" to="/workers">
                {t('My GPU computers')}
              </Link>
              <Link className="btn" to="/">
                {t('Home page')}
              </Link>
            </div>
          </div>
        </li>
      </ol>
    </>
  );
}
