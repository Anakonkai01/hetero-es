import type { Experiment } from '../types/experiment';

export type Scene = { to: string; label: string };

/** The tour a presenter walks through: the control room, the live view of the run with the most GPUs, a comparison, and the explanation. */
export function presentationScenes(
  experiments: Pick<Experiment, 'experimentId' | 'status' | 'workerIds' | 'createdAt'>[],
): Scene[] {
  const done = experiments
    .filter((e) => e.status === 'COMPLETED')
    .sort((a, b) => (b.workerIds?.length ?? 0) - (a.workerIds?.length ?? 0) || b.createdAt.localeCompare(a.createdAt));
  const scenes: Scene[] = [{ to: '/dashboard', label: 'Control room' }];
  const running = experiments.find((e) => ['RUNNING', 'STARTING', 'RECOVERING'].includes(e.status));
  const showcase = running ?? done[0];
  if (showcase)
    scenes.push({
      to: `/experiments/${showcase.experimentId}?tab=live`,
      label: running ? 'Live view' : 'Replay of a real run',
    });
  if (done.length >= 2)
    scenes.push({
      to: `/experiments/compare?ids=${done
        .slice(0, 2)
        .map((e) => e.experimentId)
        .join(',')}`,
      label: 'Comparison',
    });
  scenes.push({ to: '/explain', label: 'How it works' });
  return scenes;
}
