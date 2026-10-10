import { Link } from "react-router";
import { formatClock } from "../../lib/format";
import { EVENT_SEVERITY } from "../../lib/labels";
import type { SystemEvent } from "../../types/event";
import { Badge } from "../ui/Badge";

interface EventRowsProps {
  events: SystemEvent[];
  label: string;
}

/** Compact event list (time, level, message) used inside other pages. */
export function EventRows({ events, label }: EventRowsProps) {
  return (
    <div className="scroll">
      <div className="tw s" role="table" aria-label={label}>
        {events.map((event) => (
          <div className="row cols-dev" role="row" key={event.eventId}>
            <div className="c mono mut" role="cell">
              {formatClock(event.timestamp)}
            </div>
            <div className="c" role="cell">
              <Badge info={EVENT_SEVERITY[event.severity]} />
            </div>
            <div className="c" role="cell">
              <Link
                className="link"
                style={{ whiteSpace: "normal", color: "var(--ink)" }}
                to={`/events?selected=${event.eventId}`}
              >
                {event.message}
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
