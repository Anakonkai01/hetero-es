import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { useAppState } from "../../app/appState";
import type { Scenario } from "../../mocks/scenario";
import { formatClock } from "../../lib/format";
import { LoadingState } from "../common/LoadingState";
import {
  ChipIcon,
  DashboardIcon,
  FileIcon,
  FlaskIcon,
  ListIcon,
  LogoMark,
  RefreshIcon,
} from "../ui/Icons";
import { useStatusToasts } from "./useStatusToasts";
import { useSession } from "../../app/session";
import { IS_MOCK } from "../../lib/dataSource";

const navigationItems = [
  { label: "Workspace", path: "/workspace", icon: <DashboardIcon /> },
  { label: "Workers", path: "/workers", icon: <ChipIcon /> },
  { label: "Profile", path: "/profile", icon: <ListIcon /> },
  { label: "Models", path: "/models", icon: <FileIcon /> },
  { label: "Experiments", path: "/experiments", icon: <FlaskIcon /> },
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
  if (section === "dashboard") return "Overview";
  if (section === "workspace") return "Workspace";
  if (section === "profile") return "Profile";
  if (section === "models") return "Models";
  if (section === "scheduling") return "Worker usage";

  return "HeteroES";
}

export function AppLayout() {
  const { session, workspace, selectWorkspace, signOut } = useSession();
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

  const stale = scenario === "stale";
  const updatedAt = `${formatClock(lastUpdated)} GMT+7`;

  return (
    <div className="app">
      <aside className="side" aria-label="Primary navigation">
        <div className="brand">
          <div className="logo">
            <LogoMark />
            <b>
              Hetero<i>ES</i>
            </b>
          </div>
          <span>
            LLM post-training with Evolution Strategies on a heterogeneous
            GPU cluster.
          </span>
        </div>

        <div className="demo-form" style={{ padding: "0 10px" }}>
          <label className="fg" htmlFor="active-workspace">Workspace<select id="active-workspace" className="sel" value={workspace?.workspaceId ?? ""} onChange={(event) => { selectWorkspace(event.target.value); if (pathname.startsWith("/workspace/")) navigate(`/workspace/${event.target.value}`); }}>
            {!session?.workspaces.length && <option value="">No workspace</option>}
            {session?.workspaces.map((item) => <option value={item.workspaceId} key={item.workspaceId}>{item.name}</option>)}
          </select></label>
          <span className="hint">{session?.user.displayName}</span>
          <button type="button" className="btn" onClick={() => void signOut().catch((error: unknown) => flash(error instanceof Error ? error.message : "Could not sign out."))}>Sign out</button>
        </div>

        <nav className="navl" aria-label="Main sections">
          {navigationItems.filter((item) => IS_MOCK || item.path === '/workspace' || item.path === '/profile' || (session?.user.accountStatus === 'ACTIVE' && (workspace || item.path === '/workers'))).map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => (isActive ? "nav on" : "nav")}
            >
              {item.icon}
              {item.label}
            </NavLink>
          ))}
          {!IS_MOCK && session?.user.platformAdmin && session.user.accountStatus === 'ACTIVE' && <NavLink className={({ isActive }) => isActive ? 'nav on' : 'nav'} to="/operations"><ListIcon />Operations</NavLink>}
        </nav>

        <div className="demo">
          {IS_MOCK ? "Local MSW demo. Authentication, GPU states and runtime confirmations are simulated. Sample figures are not benchmarks." : "Private runtime · shared GPU pool · one active experiment."}
        </div>
      </aside>

      <div className="main">
        <header className="top">
          <span className="ctx">{contextName(pathname)}</span>

          <span
            className={stale ? "conn bad" : "conn"}
            title="Data source connection; individual worker connectivity is reported separately."
          >
            {stale ? "Data source disconnected" : IS_MOCK ? "Local demo API" : "Runtime API"}
          </span>

          <span className="mut" style={{ fontSize: "12.5px" }}>
            {stale
              ? `Stale data · last updated ${updatedAt}`
              : `Updated ${updatedAt}`}
          </span>

          <button
            type="button"
            className="btn"
            onClick={refresh}
            disabled={refreshing}
          >
            <RefreshIcon />
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>

          {IS_MOCK && import.meta.env.DEV && (
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <label htmlFor="simsel">Simulate state</label>
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

        <main className="content">
          {stale && (
            <div className="note warn" role="status">
              <b>Connection to the data source lost.</b> Showing stale data,
              last updated at {updatedAt}. Worker states may have changed; a
              lost connection does not mean workers are offline.{" "}
              <button type="button" className="link" onClick={refresh}>
                Retry
              </button>
            </div>
          )}

          {!IS_MOCK && session?.user.accountStatus !== 'ACTIVE' && !['/workspace','/profile'].includes(pathname) ? <p role="status">Your account is {session?.user.accountStatus}. Visit your profile or wait for administrator approval.</p> : scenario === "loading" ? <LoadingState /> : <Outlet key={`${session?.user.userId}:${workspace?.workspaceId}`} />}
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
