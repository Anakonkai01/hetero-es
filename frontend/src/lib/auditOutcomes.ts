/** Plain lines for a run's audit outcomes (`auditSummary.outcomes` from the lab supervisor). */
export interface AuditOutcomes {
  selected: number;
  matched: number;
  mismatched: number;
  pending: number;
  timedOut: number;
  skipped: number;
  unknown: number;
  enabled: boolean;
  rate: number;
  known: boolean;
  policy: 'strict-stop' | 'historical' | null;
  drainReasons: Record<string, number>;
  strictStop:
    | { candidateId: string; generation: number; originalWorker: string; auditorWorker: string }
    | { unreadable: true }
    | null;
  restoreFaults: string[];
}

export interface AuditSegment {
  template: string;
  params: Record<string, string | number>;
}

/** One line is its segments joined by " · "; each segment is translated on its own. */
export interface AuditLine {
  segments: AuditSegment[];
  tone: 'info' | 'warn' | 'err';
}

// Shown in this order; a zero count is left out so "0 mismatched" never reads as a check that ran.
const COUNTS = [
  ['matched', '{count} matched'],
  ['mismatched', '{count} mismatched'],
  ['pending', '{count} pending'],
  ['timedOut', '{count} timed out'],
  ['skipped', '{count} skipped'],
  ['unknown', '{count} unknown'],
] as const;

const SENTENCES = {
  disabled: 'Audits are disabled (rate 0)',
  chosen: 'Audit outcomes: {count} chosen',
  none: 'No candidate has been chosen for audit yet; this is not evidence that results were checked.',
  unknown: 'Some audit evidence is missing or from an older run; unknown is not a match.',
  strict: 'Strict decoder: the first audit mismatch stops the run before the next update.',
  restore: 'Exact restore failed on: {workers}',
  stop: 'Strict audit mismatch on {candidate} (generation {generation}): {original} and {auditor} produced different text. The run stopped before the next update and needs operator review.',
  unreadable: 'A strict audit stop was recorded but its receipt cannot be read; the run needs operator review.',
} as const;

/** The run's failure reason after a strict stop, as the managed runner reports it (`AuditRunGuard.fatal_error`). */
export const STRICT_STOP_FAILURE = 'CoordinatorError: Audit text mismatch requires operator review';

/** Every sentence this module can show, for the translation completeness test. */
export const AUDIT_TEMPLATES: string[] = [
  ...Object.values(SENTENCES),
  ...COUNTS.map(([, label]) => label),
  STRICT_STOP_FAILURE,
];

const line = (template: string, tone: AuditLine['tone'], params: AuditSegment['params'] = {}): AuditLine => ({
  segments: [{ template, params }],
  tone,
});

export function auditOutcomeLines(o: AuditOutcomes, names: Record<string, string> = {}): AuditLine[] {
  const name = (worker: string) => names[worker] ?? worker;
  if (!o.enabled) return [line(SENTENCES.disabled, 'warn')];
  const tone = o.mismatched ? 'err' : o.timedOut || o.skipped || o.unknown || !o.selected ? 'warn' : 'info';
  const lines: AuditLine[] = [
    {
      segments: [
        { template: SENTENCES.chosen, params: { count: o.selected } },
        ...COUNTS.filter(([key]) => o[key] > 0).map(([key, template]) => ({ template, params: { count: o[key] } })),
      ],
      tone,
    },
  ];
  if (!o.selected) lines.push(line(SENTENCES.none, 'warn'));
  if (!o.known) lines.push(line(SENTENCES.unknown, 'warn'));
  if (o.policy === 'strict-stop') lines.push(line(SENTENCES.strict, 'info'));
  if (o.restoreFaults.length)
    lines.push(line(SENTENCES.restore, 'err', { workers: o.restoreFaults.map(name).join(', ') }));
  if (o.strictStop && 'candidateId' in o.strictStop)
    lines.push(
      line(SENTENCES.stop, 'err', {
        candidate: o.strictStop.candidateId,
        generation: o.strictStop.generation + 1,
        original: name(o.strictStop.originalWorker),
        auditor: name(o.strictStop.auditorWorker),
      }),
    );
  else if (o.strictStop) lines.push(line(SENTENCES.unreadable, 'err'));
  return lines;
}
