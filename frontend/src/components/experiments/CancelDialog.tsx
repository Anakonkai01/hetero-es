import {useProduct} from '@heteroes/product-ui';
import { useRequestCancel } from "../../hooks/useExperimentMutations";
import type { Experiment } from "../../types/experiment";
import {Modal} from '../ui/Modal';

interface CancelDialogProps {
  experiment: Experiment;
  onClose: () => void;
}

export function CancelDialog({ experiment, onClose }: CancelDialogProps) {
  const {t}=useProduct();
  const cancel = useRequestCancel();
  const sending = cancel.isPending;
  const accepted = cancel.isSuccess;

  return (
    <Modal title={t('Request to cancel this experiment?')} onClose={onClose}>
      <div className="modal-form">

        <div>
          <b>{experiment.name}</b>
          <div className="mono mut">{experiment.experimentId}</div>
        </div>

        {!sending && !accepted && (
          <div className="note warn">
            {t("Sending a request does not cancel immediately. The experiment keeps its current runtime status until the coordinator confirms.")}</div>
        )}
        {sending && (
          <div className="note" role="status">
            {t("Sending cancel request…")}</div>
        )}
        {cancel.isError && (
          <div className="note err" role="alert">
            <b>{t("The request could not be sent.")}</b> {cancel.error.message}
          </div>
        )}
        {accepted && (
          <div className="note" role="status">
            <b>{t("Cancel request received.")}</b> {t("The official status will update once the coordinator confirms (simulated after a few seconds).")}</div>
        )}

        <div className="acts" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="btn" onClick={onClose}>
            {accepted ? t("Close") : t("Keep running")}
          </button>
          {!accepted && (
            <button
              type="button"
              className="btn dng"
              disabled={sending}
              onClick={() => cancel.mutate(experiment.experimentId)}
            >
              {t("Send cancel request")}</button>
          )}
        </div>
      </div>
    </Modal>
  );
}
