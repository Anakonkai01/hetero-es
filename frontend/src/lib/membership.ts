// Elastic membership (ADR-009): what the lab asked for, and what the coordinator has applied at a generation boundary.
interface Change {
  workerId: string;
  action: 'JOIN' | 'LEAVE' | 'RETRY';
}

export interface MembershipFields {
  workerIds?: string[];
  membershipRequests?: Change[];
  membership?: { members?: string[]; left?: string[] };
}

export type MemberState = 'member' | 'joining' | 'leaving' | 'left';

export function memberView(e: MembershipFields): { workerId: string; state: MemberState }[] {
  const intended = [...(e.workerIds ?? [])];
  const everyone = [...intended];
  for (const change of e.membershipRequests ?? []) {
    if (!everyone.includes(change.workerId)) everyone.push(change.workerId);
    const at = intended.indexOf(change.workerId);
    if (change.action === 'JOIN' && at < 0) intended.push(change.workerId);
    if (change.action === 'LEAVE' && at >= 0) intended.splice(at, 1);
  }
  const applied = e.membership?.members;
  const left = e.membership?.left ?? [];
  return everyone.map((workerId) => {
    if (left.includes(workerId) && !intended.includes(workerId)) return { workerId, state: 'left' };
    const wanted = intended.includes(workerId);
    const present = applied ? applied.includes(workerId) : (e.workerIds ?? []).includes(workerId);
    if (wanted && present) return { workerId, state: 'member' };
    if (wanted) return { workerId, state: 'joining' };
    return { workerId, state: present ? 'leaving' : 'left' };
  });
}
