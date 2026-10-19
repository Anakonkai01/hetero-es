import { useProduct } from '@heteroes/product-ui';
import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { isServerError } from '../api/client';
import { useAppState } from '../app/appState';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { QueryState } from '../components/common/QueryState';
import { Badge } from '../components/ui/Badge';
import { PageHeader } from '../components/ui/PageHeader';
import { useEvents } from '../hooks/useEvents';
import { useExperiments } from '../hooks/useExperiments';
import { describeEvent, fillTemplate } from '../lib/eventText';
import { formatDateTime, formatFullDateTime, shortId } from '../lib/format';
import { EVENT_SEVERITY } from '../lib/labels';
import { fromEvents } from '../lib/navigation';
import type { EventSeverity, SystemEvent } from '../types/event';

type LevelFilter = 'all' | EventSeverity;

const WORKERS_ONLY = 'workers';
const MINUTE_MS = 60_000;
const PAGE = 100;

interface RelatedLink {
  kind: string;
  label: string;
  to: string;
}

const severityOf = (tone: string): EventSeverity => (tone === 'err' ? 'ERROR' : tone === 'warn' ? 'WARNING' : 'INFO');

export function EventsPage() {
  const { t } = useProduct();
  const { retryRegion } = useAppState();
  const eventsQuery = useEvents();
  const experimentsQuery = useExperiments();
  const [params, setParams] = useSearchParams();
  const [level, setLevel] = useState<LevelFilter>('all');
  const [rangeMinutes, setRangeMinutes] = useState('all');
  const [showDetails, setShowDetails] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const [now] = useState(() => Date.now());

  const related = params.get('experiment') ?? 'all';
  const selectedId = params.get('selected');

  const events = useMemo(() => eventsQuery.data ?? [], [eventsQuery.data]);
  const experiments = experimentsQuery.data ?? [];
  const nameOf = (id?: string) =>
    (id && experiments.find((e) => e.experimentId === id)?.name) || (id ? shortId(id) : '—');

  // Newest first; routine chatter (a worker asking for work, weight clean-up) is hidden unless asked for.
  const described = useMemo(
    () =>
      [...events]
        .reverse()
        .map((event) => ({ event, d: describeEvent(event.eventType, event.details, event.workerId) })),
    [events],
  );
  const rows = described.filter(
    ({ event, d }) =>
      (showDetails || d.level === 'main' || d.tone === 'warn' || d.tone === 'err') &&
      (level === 'all' || severityOf(d.tone) === level) &&
      (rangeMinutes === 'all' || now - new Date(event.timestamp).getTime() <= Number(rangeMinutes) * MINUTE_MS) &&
      (related === 'all' ||
        (related === WORKERS_ONLY ? !event.experimentId && Boolean(event.workerId) : event.experimentId === related)),
  );
  const selected = events.find((e) => e.eventId === selectedId);
  const sentence = (event: SystemEvent) => {
    const d = describeEvent(event.eventType, event.details, event.workerId);
    return fillTemplate(t(d.template), d.params);
  };

  function updateParams(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params);

    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }

    setParams(next, { replace: true });
  }

  function clearFilters() {
    setLevel('all');
    setRangeMinutes('all');
    setShowDetails(false);
    setLimit(PAGE);
    updateParams({ experiment: null });
  }

  function linksOf(event: SystemEvent): RelatedLink[] {
    const links: RelatedLink[] = [];
    const experimentId = event.experimentId;
    const candidatePath =
      experimentId && event.generationId && event.candidateId
        ? `/experiments/${experimentId}/generations/${event.generationId}/candidates/${event.candidateId}`
        : undefined;

    if (experimentId) {
      links.push({ kind: 'Experiment', label: nameOf(experimentId), to: `/experiments/${experimentId}` });
    }

    if (experimentId && event.generationId) {
      links.push({
        kind: 'Generation',
        label: shortId(event.generationId),
        to: `/experiments/${experimentId}/generations/${event.generationId}`,
      });
    }

    if (candidatePath && event.candidateId) {
      links.push({ kind: 'Candidate', label: shortId(event.candidateId), to: candidatePath });
    }

    if (candidatePath && event.attemptId) {
      links.push({ kind: 'Attempt', label: shortId(event.attemptId), to: candidatePath });
    }

    if (event.workerId) {
      links.push({ kind: 'Worker', label: event.workerId, to: `/workers/${event.workerId}` });
    }

    return links;
  }

  const failed = eventsQuery.isError && isServerError(eventsQuery.error);
  const visible = rows.slice(0, limit);

  return (
    <QueryState
      isPending={eventsQuery.isPending}
      isError={eventsQuery.isError && !failed}
      hasData={Boolean(eventsQuery.data)}
      title={t('Could not load events')}
    >
      <PageHeader
        title={t('Events')}
        description={t(
          'What the coordinator and workers did, newest first. Routine details are hidden until you ask for them.',
        )}
      />

      <div className="split">
        <section className="card a" aria-label={t('Event log')}>
          <div className="filters" style={{ paddingTop: 16 }}>
            <div className="fg">
              <label htmlFor="f-ev-l">{t('Level')}</label>
              <select
                id="f-ev-l"
                className="sel"
                value={level}
                onChange={(event) => {
                  setLevel(event.target.value as LevelFilter);
                  setLimit(PAGE);
                }}
              >
                <option value="all">{t('All')}</option>
                <option value="ERROR">{t('ERROR')}</option>
                <option value="WARNING">{t('WARNING')}</option>
                <option value="INFO">{t('INFO')}</option>
              </select>
            </div>
            <div className="fg">
              <label htmlFor="f-ev-r">{t('Time')}</label>
              <select
                id="f-ev-r"
                className="sel"
                value={rangeMinutes}
                onChange={(event) => {
                  setRangeMinutes(event.target.value);
                  setLimit(PAGE);
                }}
              >
                <option value="all">{t('All time')}</option>
                <option value="60">{t('Last hour')}</option>
                <option value="1440">{t('Last 24 hours')}</option>
              </select>
            </div>
            <div className="fg">
              <label htmlFor="f-ev-e">{t('Related object')}</label>
              <select
                id="f-ev-e"
                className="sel"
                value={related}
                onChange={(event) => {
                  setLimit(PAGE);
                  updateParams({ experiment: event.target.value === 'all' ? null : event.target.value });
                }}
              >
                <option value="all">{t('Any object')}</option>
                {experiments.map((experiment) => (
                  <option key={experiment.experimentId} value={experiment.experimentId}>
                    {experiment.name} · {formatDateTime(experiment.createdAt)}
                  </option>
                ))}
                <option value={WORKERS_ONLY}>{t('Workers only')}</option>
              </select>
            </div>
            <label className="check-inline">
              <input
                type="checkbox"
                checked={showDetails}
                onChange={(event) => {
                  setShowDetails(event.target.checked);
                  setLimit(PAGE);
                }}
              />
              {t('Show routine details')}
            </label>
          </div>

          {failed ? (
            <ErrorState
              title={t('Could not load the event log')}
              onRetry={retryRegion}
              retryLabel="Retry this region"
            />
          ) : events.length === 0 ? (
            <EmptyState title={t('No events yet')} message="The log fills in once experiments or workers are active." />
          ) : rows.length === 0 ? (
            <EmptyState title={t('No events match the filters')}>
              <button type="button" className="btn" onClick={clearFilters}>
                {t('Clear filters')}
              </button>
            </EmptyState>
          ) : (
            <>
              <div className="scroll">
                <div className="tw s" role="table" aria-label={t('Events')}>
                  <div className="rowh cols-ev" role="row">
                    <div className="c" role="columnheader">
                      {t('Time')}
                    </div>
                    <div className="c" role="columnheader">
                      {t('Level')}
                    </div>
                    <div className="c" role="columnheader">
                      {t('Experiment')}
                    </div>
                    <div className="c" role="columnheader">
                      {t('Message')}
                    </div>
                  </div>
                  {visible.map(({ event, d }) => {
                    const isSelected = event.eventId === selectedId;

                    return (
                      <div className={isSelected ? 'row cols-ev sel' : 'row cols-ev'} role="row" key={event.eventId}>
                        <div className="c mono mut" role="cell">
                          {formatDateTime(event.timestamp)}
                        </div>
                        <div className="c" role="cell">
                          <Badge info={EVENT_SEVERITY[severityOf(d.tone)]} />
                        </div>
                        <div
                          className="c"
                          role="cell"
                          title={nameOf(event.experimentId)}
                          style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        >
                          {nameOf(event.experimentId)}
                        </div>
                        <div className="c" role="cell">
                          <button
                            type="button"
                            className="link"
                            style={{ whiteSpace: 'normal', color: 'var(--ink)', textAlign: 'left' }}
                            aria-pressed={isSelected}
                            onClick={() => updateParams({ selected: event.eventId })}
                          >
                            {sentence(event)}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="list-foot">
                <span className="hint">
                  {t('Showing')} {visible.length} {t('of')} {rows.length}
                </span>
                {rows.length > visible.length && (
                  <button type="button" className="btn" onClick={() => setLimit(limit + PAGE)}>
                    {t('Show more')}
                  </button>
                )}
              </div>
            </>
          )}
        </section>

        <section className="card b" aria-label={t('Event details')}>
          <div className="ch">
            <h2>{t('Event details')}</h2>
          </div>
          {!selected ? (
            <div className="empty">
              <span>{t('Select an event in the list to see its details and related objects.')}</span>
            </div>
          ) : (
            <div className="cb" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                <Badge
                  info={
                    EVENT_SEVERITY[
                      severityOf(describeEvent(selected.eventType, selected.details, selected.workerId).tone)
                    ]
                  }
                />
                <span className="mono mut">
                  {formatFullDateTime(selected.timestamp)} {t('GMT+7')}
                </span>
              </div>

              <div>
                <b>{sentence(selected)}</b>
              </div>

              <div>
                <div className="hint" style={{ marginBottom: 4 }}>
                  {t('Related objects')}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {linksOf(selected).map((link) => (
                    <div key={link.kind}>
                      <span className="hint">{t(link.kind)}: </span>
                      <Link className="link mono" to={link.to} state={fromEvents}>
                        {link.label}
                      </Link>
                    </div>
                  ))}
                </div>
              </div>

              <details style={{ margin: '0 -20px' }}>
                <summary>{t('Technical details')}</summary>
                <div style={{ padding: '0 20px' }}>
                  <p className="hint mono">{selected.eventType}</p>
                  <pre className="mono">
                    {JSON.stringify({ event_id: selected.eventId, ...selected.details }, null, 2)}
                  </pre>
                </div>
              </details>
            </div>
          )}
        </section>
      </div>
    </QueryState>
  );
}
