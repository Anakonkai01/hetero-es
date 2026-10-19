import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { advance, frameAt, replayStart, runBounds, type Frame, type PlayerState, type Timeline } from '../lib/runFrame';

const FLIGHT_MS = 700; // real time a packet takes to cross the diagram

export type Player = {
  frame?: Frame;
  bounds?: { startMs: number; endMs: number };
  state: PlayerState;
  live: boolean;
  play: () => void;
  pause: () => void;
  seek: (atMs: number) => void;
  setSpeed: (speed: number) => void;
  goLive: () => void;
  restart: () => void;
};

/**
 * Drives what the Live screen shows. In live mode the playhead is the server's "now"; in replay it is moved by a
 * requestAnimationFrame loop. With reduced motion the screen is refreshed a few times a second instead of every frame.
 */
export function useRunPlayer(
  timeline: Timeline | undefined,
  mode: 'live' | 'replay',
  clockOffsetMs: number,
  reducedMotion: boolean,
  options: { loop?: boolean; speed?: number; afterLive?: boolean } = {},
): Player {
  const baseBounds = useMemo(() => (timeline ? runBounds(timeline) : undefined), [timeline]);
  const [state, setState] = useState<PlayerState>({ atMs: 0, playing: mode === 'replay', speed: options.speed ?? 4 });
  const [clock, setClock] = useState(() => Date.now()); // the live playhead; refreshed by the animation loop, never read while rendering
  const [following, setFollowing] = useState(mode === 'live');
  const [seenMode, setSeenMode] = useState(mode);
  // Only a change of mode (not every new message) puts the view back on "live".
  if (seenMode !== mode) {
    setSeenMode(mode);
    setFollowing(mode === 'live');
  }
  const last = useRef<number>(0);

  // Start a replay from the beginning once the run is known.
  const started = useRef(false);
  useEffect(() => {
    if (mode === 'replay' && baseBounds && !started.current) {
      started.current = true;
      setState((s) => replayStart(baseBounds, Boolean(options.afterLive), s.speed));
    }
  }, [mode, baseBounds, options.afterLive]);
  // A looping replay (home page, dashboard) starts over a moment after it reaches the end.
  useEffect(() => {
    if (!options.loop || mode !== 'replay' || !baseBounds || state.playing || state.atMs < baseBounds.endMs) return;
    const timer = window.setTimeout(() => setState((s) => ({ ...s, atMs: baseBounds.startMs, playing: true })), 2500);
    return () => clearTimeout(timer);
  }, [options.loop, mode, baseBounds, state.playing, state.atMs]);

  useEffect(() => {
    if (!timeline) return;
    const shouldRun = (mode === 'live' && following) || state.playing;
    if (!shouldRun) return;
    let frame = 0;
    const loop = (now: number) => {
      const elapsed = last.current ? now - last.current : 0;
      last.current = now;
      if (mode === 'replay' || !following) setState((s) => advance(s, elapsed, runBounds(timeline)));
      setClock(Date.now());
      frame = requestAnimationFrame(loop);
    };
    const slow = reducedMotion ? window.setInterval(() => loop(performance.now()), 250) : undefined;
    last.current = 0;
    if (!reducedMotion) frame = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(frame);
      if (slow) clearInterval(slow);
    };
  }, [timeline, mode, following, state.playing, reducedMotion]);

  const live = mode === 'live' && following;
  const atMs = live ? clock + clockOffsetMs : state.atMs;
  // Following a live run, the end of the range is "now" (the last message may be a little older than the clock).
  const bounds = useMemo(
    () => baseBounds && (live ? { ...baseBounds, endMs: Math.max(baseBounds.endMs, atMs) } : baseBounds),
    [baseBounds, live, atMs],
  );
  const frame = useMemo(
    () => (timeline ? frameAt(timeline, atMs, { flightMs: FLIGHT_MS * (live ? 1 : state.speed) }) : undefined),
    [timeline, atMs, live, state.speed],
  );

  return {
    frame,
    bounds,
    state: live ? { ...state, atMs } : state,
    live,
    play: useCallback(() => {
      setFollowing(false);
      setState((s) =>
        bounds && s.atMs >= bounds.endMs ? { ...s, atMs: bounds.startMs, playing: true } : { ...s, playing: true },
      );
    }, [bounds]),
    pause: useCallback(() => {
      setFollowing(false);
      setState((s) => ({ ...s, atMs: live ? Date.now() + clockOffsetMs : s.atMs, playing: false }));
    }, [live, clockOffsetMs]),
    seek: useCallback((value: number) => {
      setFollowing(false);
      setState((s) => ({ ...s, atMs: value }));
    }, []),
    setSpeed: useCallback((speed: number) => setState((s) => ({ ...s, speed })), []),
    goLive: useCallback(() => {
      setFollowing(true);
      setState((s) => ({ ...s, playing: false }));
    }, []),
    restart: useCallback(() => {
      setFollowing(false);
      setState((s) => ({ ...s, atMs: bounds?.startMs ?? 0, playing: true }));
    }, [bounds]),
  };
}
