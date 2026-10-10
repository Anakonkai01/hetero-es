import { useRequestCancel } from "../../hooks/useExperimentMutations";
import type { Experiment } from "../../types/experiment";

interface CancelDialogProps {
  experiment: Experiment;
  onClose: () => void;
}

export function CancelDialog({ experiment, onClose }: CancelDialogProps) {
  const cancel = useRequestCancel();
  const sending = cancel.isPending;
  const accepted = cancel.isSuccess;

  return (
    <div className="ovl">
      <div
        className="dlg"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dlg-t"
      >
        <h2 id="dlg-t">Request to cancel this experiment?</h2>

        <div>
          <b>{experiment.name}</b>
          <div className="mono mut">{experiment.experimentId}</div>
        </div>

        {!sending && !accepted && (
          <div className="note warn">
            Sending a request does not cancel immediately. The experiment
            keeps its current runtime status until the coordinator confirms.
          </div>
        )}
        {sending && (
          <div className="note" role="status">
            Sending cancel request…
          </div>
        )}
        {cancel.isError && (
          <div className="note err" role="alert">
            <b>The request could not be sent.</b> {cancel.error.message}
          </div>
        )}
        {accepted && (
          <div className="note" role="status">
            <b>Cancel request received.</b> The official status will update
            once the coordinator confirms (simulated after a few seconds).
          </div>
        )}

        <div className="acts" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="btn" onClick={onClose}>
            {accepted ? "Close" : "Keep running"}
          </button>
          {!accepted && (
            <button
              type="button"
              className="btn dng"
              disabled={sending}
              onClick={() => cancel.mutate(experiment.experimentId)}
            >
              Send cancel request
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
