import { useProduct } from '@heteroes/product-ui';
import { Link } from "react-router";
import { describeEvent,fillTemplate } from "../../lib/eventText";
import { formatDateTime } from "../../lib/format";
import { EVENT_SEVERITY } from "../../lib/labels";
import type { SystemEvent } from "../../types/event";
import { Badge } from "../ui/Badge";

interface EventRowsProps {
  events: SystemEvent[];
  label: string;
}

/** Compact event list (time, level, message) used inside other pages. */
export function EventRows({ events, label }: EventRowsProps) {
  const {t}=useProduct();
  const describe = (event: SystemEvent) => describeEvent(event.eventType, event.details, event.workerId);
  const sentence = (event: SystemEvent) => { const d = describe(event); return fillTemplate(t(d.template), d.params); };
  const severityOf = (event: SystemEvent) => { const tone = describe(event).tone; return tone === "err" ? "ERROR" : tone === "warn" ? "WARNING" : "INFO"; };
  return (
    <div className="scroll">
      <div className="tw s" role="table" aria-label={label}>
        {events.map((event) => (
          <div className="row cols-dev" role="row" key={event.eventId}>
            <div className="c mono mut" role="cell">
              {formatDateTime(event.timestamp)}
            </div>
            <div className="c" role="cell">
              <Badge info={EVENT_SEVERITY[severityOf(event)]} />
            </div>
            <div className="c" role="cell">
              <Link
                className="link"
                style={{ whiteSpace: "normal", color: "var(--ink)" }}
                to={`/events?selected=${event.eventId}`}
              >
                {sentence(event)}
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
