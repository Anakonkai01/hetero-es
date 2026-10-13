import { useProduct } from "@heteroes/product-ui";
import { useSession } from "../../app/session";
import { useTemplateMutations, useTemplates } from "../../hooks/useTemplates";
import { BUILT_IN, type Template } from "../../lib/templates";

/** "Start from…": built-in sizes, settings saved by the workspace, or (when arriving from a run) a copy of that run. */
export function TemplatePicker({ value, onChange, cloneName }: { value: string; onChange: (id: string, template?: Template) => void; cloneName?: string }) {
  const { t } = useProduct();
  const { session, workspace } = useSession();
  const saved = useTemplates();
  const { remove } = useTemplateMutations();
  const all: Template[] = [...BUILT_IN, ...(saved.data ?? [])];
  const current = saved.data?.find(item => item.templateId === value);
  const canDelete = Boolean(current && (workspace?.role === "ADMIN" || current.ownerUserId === session?.user.userId));
  return (
    <div className="template-picker">
      <label className="fg" htmlFor="template-picker">{t("Start from")}
        <select id="template-picker" className="sel" value={value} onChange={event => onChange(event.target.value, all.find(item => item.templateId === event.target.value))}>
          <option value="">{t("Empty form")}</option>
          {cloneName && <option value="clone">{t("A copy of")} {cloneName}</option>}
          <optgroup label={t("Built-in")}>{BUILT_IN.map(item => <option key={item.templateId} value={item.templateId}>{t(item.name)}</option>)}</optgroup>
          {(saved.data?.length ?? 0) > 0 && <optgroup label={t("Saved by your workspace")}>{saved.data!.map(item => <option key={item.templateId} value={item.templateId}>{item.name}{item.ownerName ? ` · ${item.ownerName}` : ""}</option>)}</optgroup>}
        </select>
      </label>
      {canDelete && current && <button type="button" className="btn dng" disabled={remove.isPending} onClick={() => { if (window.confirm(t("Delete this template?"))) remove.mutate(current.templateId, { onSuccess: () => onChange("") }); }}>{t("Delete template")}</button>}
    </div>
  );
}
