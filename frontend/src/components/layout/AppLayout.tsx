import { PreferencesControl, useProduct } from '@heteroes/product-ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router';
import { apiGet } from '../../api/client';
import { useAppState } from '../../app/appState';
import { usePresentation } from '../../app/presentationContext';
import { useSession } from '../../app/session';
import { formatClock } from '../../lib/format';
import type { User } from '../../types/access';
import { ChipIcon, DashboardIcon, FileIcon, FlaskIcon, HomeIcon, ListIcon, LogoMark, RefreshIcon } from '../ui/Icons';
import { CommandPalette } from './CommandPalette';
import { NotificationBell } from './NotificationBell';
import { AccountMenu } from '../common/AccountMenu';
import { PresentationBar } from './PresentationBar';
import { useStatusToasts } from './useStatusToasts';
const navigationItems = [
  { label: 'Home', path: '/', icon: <HomeIcon />, always: true },
  { label: 'Get started', path: '/get-started', icon: <FileIcon />, always: true },
  { label: 'Dashboard', path: '/dashboard', icon: <DashboardIcon /> },
  { label: 'Workspace', path: '/workspace', icon: <DashboardIcon /> },
  { label: 'Workers', path: '/workers', icon: <ChipIcon /> },
  { label: 'Models', path: '/models', icon: <FileIcon /> },
  { label: 'Experiments', path: '/experiments', icon: <FlaskIcon /> },
  { label: 'Artifacts', path: '/artifacts', icon: <FileIcon /> },
  { label: 'Events', path: '/events', icon: <ListIcon /> },
];
function contextName(pathname: string): string {
  const parts = pathname.split('/').filter(Boolean);
  const [section, id, child, , grandchild] = parts;
  if (section === 'experiments') {
    if (id === 'new') return 'Create experiment';
    if (id === 'compare') return 'Compare experiments';
    if (grandchild) return 'Candidate detail';
    if (child === 'generations') return 'Generation detail';
    return id ? 'Experiment detail' : 'Experiments';
  }
  if (section === 'workers') {
    return id ? 'Worker detail' : 'Workers';
  }
  if (section === 'events') return 'Events';
  if (section === 'artifacts') return 'Artifacts';
  if (section === 'dashboard') return 'Dashboard';
  if (section === 'workspace') return 'Workspace';
  if (section === 'get-started') return 'Get started';
  if (section === 'profile') return 'Profile';
  if (section === 'models') return 'Models';
  if (section === 'operations') return 'Lab operations';
  if (section === 'scheduling') return 'Worker usage';
  return 'HeteroES';
}
export function AppLayout() {
  const { t } = useProduct();
  const [menu, setMenu] = useState(false);
  const health = useQuery({
    queryKey: ['control-health'],
    queryFn: () =>
      apiGet<{
        ok: boolean;
      }>('/api/v1/health'),
    enabled: true,
    refetchInterval: 5000,
    retry: 1,
  });
  const { session, workspace, selectWorkspace } = useSession();
  const presentation = usePresentation();
  const administrator = Boolean(session?.user.platformAdmin && session.user.accountStatus === 'ACTIVE');
  const accounts = useQuery({
    queryKey: ['platform-users', session?.user.userId],
    queryFn: () => apiGet<User[]>('/api/v1/platform/users'),
    enabled: administrator,
    refetchInterval: 10000,
  });
  const waiting = accounts.data?.filter((user) => user.accountStatus === 'PENDING').length ?? 0;
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { refresh, refreshing, lastUpdated, toast } = useAppState();
  useStatusToasts();
  const stale = health.isError;
  const updatedAt = `${formatClock(health.dataUpdatedAt || lastUpdated)} GMT+7`;
  return (
    <div className="app" data-nav-open={menu}>
      <CommandPalette />
      <PresentationBar />
      <a href="#main-content" className="skip-link">
        {t('Skip to content')}
      </a>
      <aside className="side" aria-label={t('Primary navigation')}>
        <div className="brand">
          <div className="logo">
            <Link to="/" aria-label={t('Home')}>
              <LogoMark />
            </Link>
            <b>
              {t('Hetero')}
              <i>{t('ES')}</i>
            </b>
          </div>
          <span>{t('Distributed research lab')}</span>
        </div>

        <div className="demo-form" style={{ padding: '0 10px' }}>
          <label className="fg" htmlFor="active-workspace">
            {t('Workspace')}
            <select
              id="active-workspace"
              className="sel"
              value={workspace?.workspaceId ?? ''}
              onChange={(event) => {
                selectWorkspace(event.target.value);
                if (pathname.startsWith('/workspace/')) navigate(`/workspace/${event.target.value}`);
              }}
            >
              {!session?.workspaces.length && <option value="">{t('No workspace')}</option>}
              {session?.workspaces.map((item) => (
                <option value={item.workspaceId} key={item.workspaceId}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <nav className="navl" aria-label={t('Main sections')}>
          {navigationItems
            .filter(
              (item) =>
                item.always ||
                item.path === '/workspace' ||
                item.path === '/profile' ||
                (session?.user.accountStatus === 'ACTIVE' && (workspace || item.path === '/workers')),
            )
            .map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setMenu(false)}
                end={item.path === '/'}
                className={({ isActive }) => (isActive && item.path !== '/' ? 'nav on' : 'nav')}
              >
                {item.icon}
                {t(item.label)}
              </NavLink>
            ))}
          {session?.user.platformAdmin && session.user.accountStatus === 'ACTIVE' && (
            <NavLink className={({ isActive }) => (isActive ? 'nav on' : 'nav')} to="/operations">
              <ListIcon />
              {t('Operations')}
              {waiting > 0 && (
                <span
                  className="nav-badge"
                  role="status"
                  aria-label={`${waiting} ${t('accounts waiting for approval')}`}
                >
                  {waiting}
                </span>
              )}
            </NavLink>
          )}
        </nav>
        <div className="demo">{t('Private runtime · shared GPU pool.')}</div>
      </aside>

      <div className="main">
        <header className="top">
          <button
            className="btn mobile-toggle"
            aria-label={t('Navigation')}
            aria-expanded={menu}
            onClick={() => setMenu(!menu)}
          >
            ☰
          </button>
          <span className="ctx">
            <span>{workspace?.name ?? 'HeteroES'}</span>
            <span aria-hidden="true"> / </span>
            <b>{t(contextName(pathname))}</b>
          </span>

          <span
            className={stale ? 'conn bad' : 'conn'}
            title={t('Data source connection; individual worker connectivity is reported separately.')}
          >
            {stale ? t('Data source disconnected') : health.isPending ? t('CONNECTING') : t('Control API')}
          </span>

          <span className="mut" style={{ fontSize: '12.5px' }}>
            {stale ? `${t('Stale data · last updated')} ${updatedAt}` : `${t('Updated')} ${updatedAt}`}
          </span>

          <button type="button" className="btn" onClick={refresh} disabled={refreshing}>
            <RefreshIcon />
            {refreshing ? t('Refreshing…') : t('Refresh')}
          </button>

          {session && (
            <button
              type="button"
              className="btn"
              aria-pressed={presentation.on}
              onClick={presentation.toggle}
              title={t('Presentation mode: larger text, no technical IDs')}
            >
              ▶ {t('Present')}
            </button>
          )}
          {session && <NotificationBell />}
          <PreferencesControl />
          <AccountMenu />
        </header>

        <main className="content" id="main-content" tabIndex={-1}>
          {stale && (
            <div className="note warn" role="status">
              <b>{t('Connection to the data source lost.')}</b> {t('Showing stale data, last updated at')}
              {updatedAt}
              {t('. Worker states may have changed; a lost connection does not mean workers are offline.')}{' '}
              <button type="button" className="link" onClick={refresh}>
                {t('Retry')}
              </button>
            </div>
          )}

          {administrator && waiting > 0 && pathname !== '/operations' && (
            <div className="note warn approval-banner" role="status">
              <b>
                {waiting} {t(waiting === 1 ? 'account is waiting for approval.' : 'accounts are waiting for approval.')}
              </b>{' '}
              <Link to="/operations">{t('Review requests')}</Link>
            </div>
          )}

          {session?.user.accountStatus !== 'ACTIVE' &&
          !['/workspace', '/profile', '/get-started'].includes(pathname) ? (
            <p role="status">
              {t('Your account is')}
              {session?.user.accountStatus}
              {t('. Visit your profile or wait for administrator approval.')}
            </p>
          ) : (
            <Outlet key={`${session?.user.userId}:${workspace?.workspaceId}`} />
          )}
        </main>
      </div>

      {toast && (
        <div className="toast" role="status" aria-live="polite">
          {toast}
        </div>
      )}
    </div>
  );
}
