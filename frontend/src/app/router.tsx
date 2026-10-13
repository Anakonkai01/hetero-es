import {lazy,Suspense} from 'react';
import {LoadingState} from '../components/common/LoadingState';
import { useSession } from "./session";

import { Navigate, Route, Routes } from "react-router";

import { AppLayout } from "../components/layout/AppLayout";

import { RequireSession } from "../components/layout/RequireSession";

import { IS_MOCK } from '../lib/dataSource';

import {HomePage} from '../pages/HomePage';

const ProfilePage=lazy(()=>import('../pages/ProfilePage').then(module=>({default:module.ProfilePage})));
const MyWorkersPage=lazy(()=>import('../pages/MyWorkersPage').then(module=>({default:module.MyWorkersPage})));
const WorkspaceListPage=lazy(()=>import('../pages/WorkspaceListPage').then(module=>({default:module.WorkspaceListPage})));
const ExperimentCreatePage=lazy(()=>import('../pages/ExperimentCreatePage').then(module=>({default:module.ExperimentCreatePage})));
const ExperimentDetailPage=lazy(()=>import('../pages/ExperimentDetailPage').then(module=>({default:module.ExperimentDetailPage})));
const ExperimentsPage=lazy(()=>import('../pages/ExperimentsPage').then(module=>({default:module.ExperimentsPage})));
const NotFoundPage=lazy(()=>import('../pages/NotFoundPage').then(module=>({default:module.NotFoundPage})));
const WorkerDetailPage=lazy(()=>import('../pages/WorkerDetailPage').then(module=>({default:module.WorkerDetailPage})));
const CandidateDetailPage=lazy(()=>import('../pages/CandidateDetailPage').then(module=>({default:module.CandidateDetailPage})));
const GenerationDetailPage=lazy(()=>import('../pages/GenerationDetailPage').then(module=>({default:module.GenerationDetailPage})));
const LoginPage=lazy(()=>import('../pages/LoginPage').then(module=>({default:module.LoginPage})));
const WorkspaceDetailRoute=lazy(()=>import('../pages/WorkspaceDetailRoute').then(module=>({default:module.WorkspaceDetailRoute})));
const ModelsPage=lazy(()=>import('../pages/ModelsPage').then(module=>({default:module.ModelsPage})));
const RegisterPage=lazy(()=>import('../pages/RegisterPage').then(module=>({default:module.RegisterPage})));
const LabOperationsPage=lazy(()=>import('../pages/LabOperationsPage').then(module=>({default:module.LabOperationsPage})));
const DashboardPage=lazy(()=>import('../pages/DashboardPage').then(module=>({default:module.DashboardPage})));
const EventsPage=lazy(()=>import('../pages/EventsPage').then(module=>({default:module.EventsPage})));
const ExplainPage=lazy(()=>import('../pages/ExplainPage').then(module=>({default:module.ExplainPage})));
const ComparePage=lazy(()=>import('../pages/ComparePage').then(module=>({default:module.ComparePage})));
const GetStartedPage=lazy(()=>import('../pages/GetStartedPage').then(module=>({default:module.GetStartedPage})));
const ArtifactsPage=lazy(()=>import('../pages/ArtifactsPage').then(module=>({default:module.ArtifactsPage})));

export function AppRouter() {
  return (
    <Suspense fallback={<LoadingState/>}><Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/explain" element={<ExplainPage />} />
      {!IS_MOCK && <Route path="/register" element={<RegisterPage />} />}
      <Route element={<RequireSession />}>
      <Route element={<AppLayout />}>
        <Route path="/get-started" element={<GetStartedPage />} />
        <Route path="/workspace" element={<WorkspaceListPage />} />
        <Route path="/workspace/current" element={<ActiveWorkspaceRedirect />} />
        <Route path="/workspace/:workspaceId" element={<WorkspaceDetailRoute />} />
        <Route path="/profile" element={<ProfilePage />} />
        {!IS_MOCK && <Route path="/operations" element={<LabOperationsPage />} />}
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/scheduling" element={<Navigate to="/experiments" replace />} />

        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/workers" element={<MyWorkersPage />} />
        <Route
          path="/workers/:workerId"
          element={<WorkerDetailPage />}
        />
        <Route path="/experiments" element={<ExperimentsPage />} />
        <Route path="/experiments/compare" element={<ComparePage />} />
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
        <Route path="/events" element={<EventsPage />} />
        <Route path="/artifacts" element={<ArtifactsPage />} />

        <Route path="*" element={<NotFoundPage />} />
      </Route>
      </Route>
    </Routes></Suspense>
  );
}

function ActiveWorkspaceRedirect() { const { workspace } = useSession(); return <Navigate to={workspace ? `/workspace/${workspace.workspaceId}` : "/workspace"} replace />; }
