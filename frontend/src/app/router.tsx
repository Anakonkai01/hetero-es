import { useSession } from "./session";
import { ProfilePage } from "../pages/ProfilePage";
import { MyWorkersPage } from "../pages/MyWorkersPage";
import { WorkspaceListPage } from "../pages/WorkspaceListPage";
import { Navigate, Route, Routes } from "react-router";
import { ExperimentCreatePage } from "../pages/ExperimentCreatePage";
import { ExperimentDetailPage } from "../pages/ExperimentDetailPage";
import { AppLayout } from "../components/layout/AppLayout";
import { ExperimentsPage } from "../pages/ExperimentsPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { WorkerDetailPage } from "../pages/WorkerDetailPage";
import { CandidateDetailPage } from "../pages/CandidateDetailPage";
import { GenerationDetailPage } from "../pages/GenerationDetailPage";
import { LoginPage } from "../pages/LoginPage";
import { WorkspaceDetailRoute } from "../pages/WorkspaceDetailRoute";
import { ModelsPage } from "../pages/ModelsPage";
import { RequireSession } from "../components/layout/RequireSession";
import { RegisterPage } from '../pages/RegisterPage';
import { LabOperationsPage } from '../pages/LabOperationsPage';
import { IS_MOCK } from '../lib/dataSource';

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      {!IS_MOCK && <Route path="/register" element={<RegisterPage />} />}
      <Route element={<RequireSession />}>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/workspace" replace />} />
        <Route path="/workspace" element={<WorkspaceListPage />} />
        <Route path="/workspace/current" element={<ActiveWorkspaceRedirect />} />
        <Route path="/workspace/:workspaceId" element={<WorkspaceDetailRoute />} />
        <Route path="/profile" element={<ProfilePage />} />
        {!IS_MOCK && <Route path="/operations" element={<LabOperationsPage />} />}
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/scheduling" element={<Navigate to="/experiments" replace />} />

        <Route path="/dashboard" element={<Navigate to="/experiments" replace />} />
        <Route path="/workers" element={<MyWorkersPage />} />
        <Route
          path="/workers/:workerId"
          element={<WorkerDetailPage />}
        />
        <Route path="/experiments" element={<ExperimentsPage />} />
        <Route
          path="/experiments/new"
          element={<ExperimentCreatePage />}
        />
        <Route
          path="/experiments/:experimentId"
          element={<ExperimentDetailPage />}
        />
        <Route
          path="/experiments/:experimentId/generations/:generationId/candidates/:candidateId"
          element={<CandidateDetailPage />}
        />
        <Route
          path="/experiments/:experimentId/generations/:generationId"
          element={<GenerationDetailPage />}
        />
        <Route path="/events" element={<Navigate to="/experiments" replace />} />
        <Route path="/artifacts" element={<Navigate to="/experiments" replace />} />

        <Route path="*" element={<NotFoundPage />} />
      </Route>
      </Route>
    </Routes>
  );
}

function ActiveWorkspaceRedirect() { const { workspace } = useSession(); return <Navigate to={workspace ? `/workspace/${workspace.workspaceId}` : "/workspace"} replace />; }
