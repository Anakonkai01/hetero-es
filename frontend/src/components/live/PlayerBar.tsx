import { useProduct } from '@heteroes/product-ui';
import type { Player } from '../../hooks/useRunPlayer';
import type { TimelineSource } from '../../hooks/useRunTimeline';
import { formatDuration } from '../../lib/diagramLayout';

const SPEEDS = [1, 4, 16, 64];

export function PlayerBar({
  player,
  mode,
  source,
}: {
  player: Player;
  mode: 'live' | 'replay';
  source?: TimelineSource;
}) {
  const { t } = useProduct();
  const { bounds, state } = player;
  if (!bounds) return null;
  const span = Math.max(1, bounds.endMs - bounds.startMs);
  // Following a live run counts as playing: the way to stop it is Pause.
  const running = state.playing || player.live;
  const value = Math.round(
    ((Math.min(Math.max(state.atMs, bounds.startMs), bounds.endMs) - bounds.startMs) / span) * 1000,
  );
  return (
    <div className="lv-player" role="group" aria-label={t('Playback controls')}>
      <button type="button" className="btn" onClick={player.restart} aria-label={t('Restart')}>
        ⏮
      </button>
      <button
        type="button"
        className="btn pri"
        onClick={running ? player.pause : player.play}
        aria-label={t(running ? 'Pause' : 'Play')}
      >
        {running ? '⏸' : '▶'}
      </button>
      <input
        className="lv-scrub"
        type="range"
        min={0}
        max={1000}
        value={value}
        aria-label={t('Position in the run')}
        onChange={(event) => player.seek(bounds.startMs + (Number(event.target.value) / 1000) * span)}
      />
      <span className="mono lv-time">
        {formatDuration(state.atMs - bounds.startMs)} / {formatDuration(span)}
      </span>
      <span className="lv-speeds" role="group" aria-label={t('Playback speed')}>
        {SPEEDS.map((speed) => (
          <button
            key={speed}
            type="button"
            className={!player.live && state.speed === speed ? 'btn pri' : 'btn'}
            aria-pressed={!player.live && state.speed === speed}
            onClick={() => player.setSpeed(speed)}
          >
            {speed}×
          </button>
        ))}
      </span>
      {mode === 'live' && (
        <button
          type="button"
          className={player.live ? 'btn pri lv-live-on' : 'btn'}
          onClick={player.goLive}
          aria-pressed={player.live}
        >
          <span className="lv-live-dot" aria-hidden="true" /> {t('Live')}
        </button>
      )}
      {mode === 'live' && source === 'polling' && <span className="hint">{t('Refreshing every few seconds')}</span>}
    </div>
  );
}
