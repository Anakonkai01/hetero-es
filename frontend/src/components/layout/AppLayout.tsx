import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { useAppState } from "../../app/appState";
import type { Scenario } from "../../mocks/scenario";
import { formatClock } from "../../lib/format";
import { LoadingState } from "../common/LoadingState";
import {
  ChipIcon,
  DashboardIcon,
  FileIcon,
  HomeIcon,
  FlaskIcon,
  ListIcon,
  LogoMark,
  RefreshIcon,
} from "../ui/Icons";
import { useStatusToasts } from "./useStatusToasts";
import { useSession } from "../../app/session";
import { IS_MOCK } from "../../lib/dataSource";
import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {apiGet} from '../../api/client';
import {PreferencesControl,useProduct} from '@heteroes/product-ui';
import type {User} from '../../types/access';

const navigationItems = [
  { label: "Home", path: "/", icon: <HomeIcon />, always: true },
  { label: "Get started", path: "/get-started", icon: <FileIcon />, always: true },
  { label: "Dashboard", path: "/dashboard", icon: <DashboardIcon /> },
  { label: "Workspace", path: "/workspace", icon: <DashboardIcon /> },
  { label: "Workers", path: "/workers", icon: <ChipIcon /> },
  { label: "Models", path: "/models", icon: <FileIcon /> },
  { label: "Experiments", path: "/experiments", icon: <FlaskIcon /> },
  { label: "Artifacts", path: "/artifacts", icon: <FileIcon /> },
  { label: "Events", path: "/events", icon: <ListIcon /> },
];

const scenarioOptions: { value: Scenario; label: string }[] = [
  { value: "normal", label: "Normal" },
  { value: "loading", label: "First load" },
  { value: "empty", label: "No data yet" },
  { value: "error", label: "Region error" },
  { value: "stale", label: "Disconnected / stale" },
  { value: "notfound", label: "Object not found" },
];

function contextName(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  const [section, id, child, , grandchild] = parts;

  if (section === "experiments") {
    if (id === "new") return "Create experiment";
    if (grandchild) return "Candidate detail";
    if (child === "generations") return "Generation detail";
    return id ? "Experiment detail" : "Experiments";
  }

  if (section === "workers") {
    return id ? "Worker detail" : "Workers";
  }

  if (section === "events") return "Events";
  if (section === "artifacts") return "Artifacts";
  if (section === "dashboard") return "Dashboard";
  if (section === "workspace") return "Workspace";
  if (section === "get-started") return "Get started";
  if (section === "profile") return "Profile";
  if (section === "models") return "Models";
  if (section === "operations") return "Lab operations";
  if (section === "scheduling") return "Worker usage";

  return "HeteroES";
}

export function AppLayout() {
  const {t}=useProduct();
  const [menu,setMenu]=useState(false);
  const health=useQuery({queryKey:['control-health'],queryFn:()=>apiGet<{ok:boolean}>('/api/v1/health'),enabled:!IS_MOCK,refetchInterval:5000,retry:1});
  const { session, workspace, selectWorkspace, signOut } = useSession();
  const administrator = !IS_MOCK && Boolean(session?.user.platformAdmin && session.user.accountStatus === 'ACTIVE');
  const accounts = useQuery({ queryKey: ['platform-users', session?.user.userId], queryFn: () => apiGet<User[]>('/api/v1/platform/users'), enabled: administrator, refetchInterval: 10000 });
  const waiting = accounts.data?.filter(user => user.accountStatus === 'PENDING').length ?? 0;
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const {
    scenario,
    setScenario,
    refresh,
    refreshing,
    lastUpdated,
    toast,
    flash,
  } = useAppState();

  useStatusToasts();

  const stale = IS_MOCK ? scenario === "stale" : health.isError;
  const updatedAt = `${formatClock(IS_MOCK?lastUpdated:health.dataUpdatedAt||lastUpdated)} GMT+7`;

  return (
    <div className="app" data-nav-open={menu}>
      <a href="#main-content" className="skip-link">{t('Skip to content')}</a>
      <aside className="side" aria-label={t("Primary navigation")}>
        <div className="brand">
          <div className="logo">
            <Link to="/" aria-label={t("Home")}><LogoMark /></Link>
            <b>
              {t("Hetero")}<i>{t("ES")}</i>
            </b>
          </div>
          <span>
            {t("Distributed research lab")}</span>
        </div>

        <div className="demo-form" style={{ padding: "0 10px" }}>
          <label className="fg" htmlFor="active-workspace">{t("Workspace")}<select id="active-workspace" className="sel" value={workspace?.workspaceId ?? ""} onChange={(event) => { selectWorkspace(event.target.value); if (pathname.startsWith("/workspace/")) navigate(`/workspace/${event.target.value}`); }}>
            {!session?.workspaces.length && <option value="">{t("No workspace")}</option>}
            {session?.workspaces.map((item) => <option value={item.workspaceId} key={item.workspaceId}>{item.name}</option>)}
          </select></label>

        </div>

        <nav className="navl" aria-label={t("Main sections")}>
          {navigationItems.filter((item) => IS_MOCK || item.always || item.path === '/workspace' || item.path === '/profile' || (session?.user.accountStatus === 'ACTIVE' && (workspace || item.path === '/workers'))).map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={()=>setMenu(false)}
              end={item.path === '/'}
              className={({ isActive }) => (isActive && item.path !== '/' ? "nav on" : "nav")}
            >
              {item.icon}
              {t(item.label)}
            </NavLink>
          ))}
          {!IS_MOCK && session?.user.platformAdmin && session.user.accountStatus === 'ACTIVE' && <NavLink className={({ isActive }) => isActive ? 'nav on' : 'nav'} to="/operations"><ListIcon />{t("Operations")}{waiting > 0 && <span className="nav-badge" role="status" aria-label={`${waiting} ${t('accounts waiting for approval')}`}>{waiting}</span>}</NavLink>}
        </nav>
        <div className="side-account"><Link to="/profile" className="account-link"><span className="account-avatar">{session?.user.displayName?.slice(0,1).toUpperCase()??'H'}</span><span><b>{session?.user.displayName}</b><small>{t(session?.user.platformAdmin?'Platform administrator':'Member')}</small></span></Link><button type="button" className="link" onClick={() => void signOut().catch((error: unknown) => flash(error instanceof Error ? error.message : "Could not sign out."))}>{t("Sign out")}</button></div>

        <div className="demo">
          {IS_MOCK ? t("Local MSW demo. Authentication, GPU states and runtime confirmations are simulated. Sample figures are not benchmarks.") : t("Private runtime · shared GPU pool.")}
        </div>
      </aside>

      <div className="main">
        <header className="top">
          <button className="btn mobile-toggle" aria-label={t('Navigation')} aria-expanded={menu} onClick={()=>setMenu(!menu)}>☰</button>
          <span className="ctx"><span>{workspace?.name??"HeteroES"}</span><span aria-hidden="true"> / </span><b>{t(contextName(pathname))}</b></span>

          <span
            className={stale ? "conn bad" : "conn"}
            title={t("Data source connection; individual worker connectivity is reported separately.")}
          >
            {stale ? t('Data source disconnected') : IS_MOCK ? t('Local demo API') : health.isPending ? t('CONNECTING') : t('Control API')}
          </span>

          <span className="mut" style={{ fontSize: "12.5px" }}>
            {stale
              ? `${t('Stale data · last updated')} ${updatedAt}`
              : `${t('Updated')} ${updatedAt}`}
          </span>

          <button
            type="button"
            className="btn"
            onClick={refresh}
            disabled={refreshing}
          >
            <RefreshIcon />
            {refreshing ? t("Refreshing…") : t("Refresh")}
          </button>

          <PreferencesControl/>
          {IS_MOCK && import.meta.env.DEV && (
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <label htmlFor="simsel">{t("Simulate state")}</label>
              <select
                id="simsel"
                className="sel"
                value={scenario}
                onChange={(event) =>
                  setScenario(event.target.value as Scenario)
                }
              >
                {scenarioOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </span>
          )}
        </header>

        <main className="content" id="main-content" tabIndex={-1}>
          {stale && (
            <div className="note warn" role="status">
              <b>{t("Connection to the data source lost.")}</b> {t("Showing stale data, last updated at")}{updatedAt}{t(". Worker states may have changed; a lost connection does not mean workers are offline.")}{" "}
              <button type="button" className="link" onClick={refresh}>
                {t("Retry")}</button>
            </div>
          )}

          {administrator && waiting > 0 && pathname !== '/operations' && <div className="note warn approval-banner" role="status"><b>{waiting} {t(waiting === 1 ? 'account is waiting for approval.' : 'accounts are waiting for approval.')}</b> <Link to="/operations">{t('Review requests')}</Link></div>}

          {!IS_MOCK && session?.user.accountStatus !== 'ACTIVE' && !['/workspace','/profile','/get-started'].includes(pathname) ? <p role="status">{t("Your account is")}{session?.user.accountStatus}{t(". Visit your profile or wait for administrator approval.")}</p> : scenario === "loading" ? <LoadingState /> : <Outlet key={`${session?.user.userId}:${workspace?.workspaceId}`} />}
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
