import { useEffect } from 'react';
import { useParams } from 'react-router';
import { useSession } from '../app/session';
import { LoadingState } from '../components/common/LoadingState';
import { ObjectNotFound } from '../components/common/ObjectNotFound';
import { WorkspacePage } from './WorkspacePage';
export function WorkspaceDetailRoute() {
  const { workspaceId } = useParams();
  const { session, workspace, selectWorkspace } = useSession();
  const member = session?.workspaces.some((w) => w.workspaceId === workspaceId);
  useEffect(() => {
    if (member && workspaceId && workspace?.workspaceId !== workspaceId) selectWorkspace(workspaceId);
  }, [member, workspaceId, workspace?.workspaceId, selectWorkspace]);
  if (!member) return <ObjectNotFound backTo="/workspace" backLabel="Workspaces" />;
  if (workspace?.workspaceId !== workspaceId) return <LoadingState />;
  return <WorkspacePage />;
}
