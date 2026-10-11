import {useProduct} from '@heteroes/product-ui';
import { useEffect, useId, useRef, type ReactNode } from "react";

export function Modal({ title, subtitle, onClose, children }: { title: string; subtitle?: string; onClose: () => void; children: ReactNode }) {
  const {t}=useProduct();
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog className="workspace-dialog" ref={ref} aria-labelledby={titleId} onCancel={onClose} onClick={(e) => { if (e.target === e.currentTarget) { const r = e.currentTarget.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) onClose(); } }}>
    <div className="modal-heading"><div><h2 id={titleId}>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="modal-close" type="button" aria-label={t("Close dialog")} onClick={onClose}>×</button></div>
    {children}
  </dialog>;
}
