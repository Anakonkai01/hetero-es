import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { apiGet, apiPatch, apiPost } from '../api/client';
import { useSession } from '../app/session';
import type { User } from '../types/access';
import type { Worker } from '../types/worker';

interface Operations {
  cloudStorageConfigured?: boolean;
  recoveryStorageConfigured?: boolean;
  metadataBackup?: { status: string; createdAt: number; errorType?: string } | null;
  dispatchHeld: boolean;
  queueCount: number;
  runtimeIssue: string | null;
  productService: string;
  runtimeService: string;
  quarantinedWorkerIds?: string[];
  workers: Worker[];
  reservations: {
    runId: string;
    status: string;
    failureReason?: string;
    workerStates: Record<string, { alive?: boolean; confirmed?: boolean }>;
  }[];
  recentFailures?: { runId: string; status: string; failureReason: string }[];
}
interface Audit {
  sequence: number;
  actor: string;
  action: string;
  target: string;
  created: string;
}
type Action = { path: string; body?: unknown; method?: 'PATCH' | 'POST' };
export function useLabOperations() {
  const { session, refreshSession } = useSession();
  const cache = useQueryClient();
  const allowed = Boolean(session?.user.platformAdmin && session.user.accountStatus === 'ACTIVE');
  const users = useQuery({
    queryKey: ['platform-users', session?.user.userId],
    queryFn: () => apiGet<User[]>('/api/v1/platform/users'),
    enabled: allowed,
    refetchInterval: 5000,
  });
  const ops = useQuery({
    queryKey: ['platform-operations', session?.user.userId],
    queryFn: () => apiGet<Operations>('/api/v1/platform/operations'),
    enabled: allowed,
    refetchInterval: 5000,
  });
  const audit = useQuery({
    queryKey: ['platform-audit', session?.user.userId],
    queryFn: () => apiGet<Audit[]>('/api/v1/platform/audit'),
    enabled: allowed,
    refetchInterval: 5000,
  });
  const [confirmed, setConfirmed] = useState(false);
  const [notice, setNotice] = useState('');
  const action = useMutation({
    mutationFn: (a: Action) => (a.method === 'PATCH' ? apiPatch(a.path, a.body) : apiPost(a.path, a.body)),
    onSuccess: async () => {
      await cache.invalidateQueries();
      await refreshSession();
    },
  });
  const pending = users.data?.filter((user) => user.accountStatus === 'PENDING') ?? [];
  const others = users.data?.filter((user) => user.accountStatus !== 'PENDING') ?? [];

  function update(user: User, body: unknown, message = '') {
    setNotice('');
    action.mutate(
      { path: `/api/v1/platform/users/${user.userId}`, method: 'PATCH', body },
      { onSuccess: () => setNotice(message) },
    );
  }
  return { session, allowed, users, ops, audit, confirmed, setConfirmed, notice, action, pending, others, update };
}
