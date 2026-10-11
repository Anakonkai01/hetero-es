import {useProduct} from '@heteroes/product-ui';
import { useState } from "react";
import { createMyWorker } from "../../api/access";
import { useAccessMutation } from "../../hooks/useAccess";
import { Modal } from "../ui/Modal";
import type { Worker } from "../../types/worker";

export function WorkerRegistration({ onClose, onRegistered }: { onClose: () => void; onRegistered: (worker: Worker) => void }) {
  const {t}=useProduct();
  const create = useAccessMutation(createMyWorker);
  const [gpuName, setName] = useState(""); const [vram, setVram] = useState(12);
  return <Modal title={t("Register Worker")} subtitle="GPU registration · Local simulation" onClose={onClose}>
    <form className="modal-form" onSubmit={(e) => { e.preventDefault(); void create.mutateAsync({ gpuName, vramTotalMb: vram * 1024 }).then(onRegistered).catch(() => {}); }}>
      <div className="registration-banner"><span className="resource-glyph">{t("GPU")}</span><div><b>{t("Hardware profile")}</b><p>{t("Registration and workspace admission are separate.")}</p></div></div>
      <label className="fg">{t("GPU name")}<input className="inp" autoFocus required maxLength={160} placeholder={t("e.g. NVIDIA RTX 4090")} value={gpuName} onChange={(e) => setName(e.target.value)} /></label>
      <label className="fg">{t("VRAM (GiB)")}<input className="inp" type="number" required min={1} max={1024} step={1} value={vram} onChange={(e) => setVram(Number(e.target.value))} /></label>
      {create.error && <p className="note err" role="alert">{create.error.message}</p>}
      <div className="modal-footer"><button type="button" className="btn" onClick={onClose}>{t("Cancel")}</button><button className="btn accent" disabled={create.isPending}>{create.isPending ? t("Registering…") : t("Register Worker")}</button></div>
    </form>
  </Modal>;
}
