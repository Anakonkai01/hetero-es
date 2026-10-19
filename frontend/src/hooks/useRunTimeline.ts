import { useEffect, useRef, useState } from 'react';
import { apiGet, readStream } from '../api/client';
import { applyDelta, type Timeline } from '../lib/runFrame';

export type TimelineSource = 'loading' | 'stream' | 'polling' | 'done' | 'error';
const POLL_MS = 2500;
const RETRY_STREAM_MS = 15000;

/**
 * The timeline of one run, kept fresh while it runs: pushed over the event stream, with a quiet fall-back to polling
 * (and a periodic attempt to get the stream back) so a proxy that buffers or a dropped connection never leaves a blank screen.
 */
export function useRunTimeline(
  runId: string,
  enabled = true,
): { timeline?: Timeline; source: TimelineSource; clockOffsetMs: number } {
  const [timeline, setTimeline] = useState<Timeline>();
  const [source, setSource] = useState<TimelineSource>('loading');
  const [clockOffsetMs, setOffset] = useState(0);
  const latest = useRef<Timeline | undefined>(undefined);
  // Another run (or the view switched off): start again from nothing. Adjusting state while rendering is the supported way.
  const [watched, setWatched] = useState(`${runId}:${enabled}`);
  if (watched !== `${runId}:${enabled}`) {
    setWatched(`${runId}:${enabled}`);
    setTimeline(undefined);
    setSource('loading');
  }

  useEffect(() => {
    if (!enabled || !runId) return;
    const stop = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    latest.current = undefined;

    const accept = (incoming: Timeline) => {
      const next = applyDelta(latest.current, incoming);
      if (next !== latest.current) {
        latest.current = next;
        setTimeline(next);
        // How far this computer's clock is from the server's, so "now" on screen means the server's now.
        setOffset(next.nowMs - Date.now());
      }
    };
    const finished = (value: Timeline) => ['COMPLETED', 'CANCELLED', 'FAILED'].includes(value.experiment.status ?? '');

    const poll = async () => {
      try {
        const value = await apiGet<Timeline>(`/api/v1/experiments/${encodeURIComponent(runId)}/timeline`);
        if (stop.signal.aborted) return;
        accept(value);
        if (finished(value)) {
          setSource('done');
          return;
        }
        setSource('polling');
      } catch {
        if (stop.signal.aborted) return;
        setSource(latest.current ? 'polling' : 'error');
      }
      timer = setTimeout(() => void cycle(), POLL_MS);
    };

    let lastStreamTry = 0;
    const cycle = async () => {
      if (stop.signal.aborted) return;
      if (Date.now() - lastStreamTry < RETRY_STREAM_MS) return poll();
      lastStreamTry = Date.now();
      let ended = false;
      try {
        await readStream(
          `/api/v1/experiments/${encodeURIComponent(runId)}/stream`,
          (message) => {
            if (message.event === 'timeline') {
              accept(JSON.parse(message.data) as Timeline);
              setSource('stream');
            }
            if (message.event === 'end') ended = true;
          },
          stop.signal,
        );
      } catch {
        if (stop.signal.aborted) return;
      }
      if (stop.signal.aborted) return;
      if (ended) {
        setSource('done');
        return;
      }
      return poll();
    };

    void cycle();
    return () => {
      stop.abort();
      if (timer) clearTimeout(timer);
    };
  }, [runId, enabled]);

  return { timeline, source, clockOffsetMs };
}
