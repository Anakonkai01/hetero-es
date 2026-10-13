import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useProduct } from "@heteroes/product-ui";
import { usePresentation } from "../../app/presentationContext";
import { useSession } from "../../app/session";
import { useExperiments } from "../../hooks/useExperiments";
import { useWorkers } from "../../hooks/useWorkers";
import { IS_MOCK } from "../../lib/dataSource";
import { commandRank } from "../../lib/esExplain";

type Command = { id: string; label: string; group: string; hint?: string; run: () => void };

/** Ctrl+K (or ⌘K): jump to a page, an experiment or a GPU, or do a common action, by typing a few letters. */
export function CommandPalette() {
  const { t, preferences, setPreferences } = useProduct();
  const navigate = useNavigate();
  const { session, signOut } = useSession();
  const presentation = usePresentation();
  const experiments = useExperiments();
  const workers = useWorkers();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const opener = useRef<Element | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const close = useCallback(() => { setOpen(false); setQuery(""); setActive(0); (opener.current as HTMLElement | null)?.focus?.(); }, []);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (!session) return;
        opener.current = document.activeElement;
        setOpen(value => !value);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [session]);

  const commands = useMemo<Command[]>(() => {
    const go = (to: string) => () => navigate(to);
    const pages: [string, string][] = [["Home", "/"], ["Get started", "/get-started"], ["Dashboard", "/dashboard"], ["Workspace", "/workspace"], ["Workers", "/workers"], ["Models", "/models"], ["Experiments", "/experiments"], ["Artifacts", "/artifacts"], ["Events", "/events"], ["Profile", "/profile"], ["How it works", "/explain"]];
    if (session?.user.platformAdmin) pages.push(["Operations", "/operations"]);
    const list: Command[] = pages.map(([label, to]) => ({ id: `page:${to}`, label: t(label), group: t("Pages"), run: go(to) }));
    if (!IS_MOCK) list.push({ id: "act:new", label: t("Create experiment"), group: t("Actions"), run: go("/experiments/new") });
    list.push(
      { id: "act:present", label: t(presentation.on ? "Exit presentation" : "Start presentation"), group: t("Actions"), run: presentation.toggle },
      { id: "act:lang", label: preferences.language === "vi" ? "English" : "Tiếng Việt", hint: t("Language"), group: t("Actions"), run: () => setPreferences({ language: preferences.language === "vi" ? "en" : "vi" }) },
      { id: "act:theme", label: t(preferences.theme === "dark" ? "Light theme" : "Dark theme"), group: t("Actions"), run: () => setPreferences({ theme: preferences.theme === "dark" ? "light" : "dark" }) },
      { id: "act:out", label: t("Sign out"), group: t("Actions"), run: () => void signOut() },
    );
    for (const experiment of [...(experiments.data ?? [])].sort((a, b) => b.createdAt.localeCompare(a.createdAt)).slice(0, 40)) list.push({ id: `run:${experiment.experimentId}`, label: experiment.name, hint: experiment.status, group: t("Experiments"), run: go(`/experiments/${experiment.experimentId}`) });
    for (const worker of workers.data ?? []) list.push({ id: `gpu:${worker.workerId}`, label: worker.displayName ?? worker.workerId, hint: worker.profile.gpuName, group: t("GPUs"), run: go(`/workers/${worker.workerId}`) });
    return list;
  }, [t, navigate, session, presentation.on, presentation.toggle, preferences, setPreferences, signOut, experiments.data, workers.data]);

  const results = useMemo(() => commandRank(commands, query).slice(0, 12), [commands, query]);
  useEffect(() => { if (open) input.current?.focus(); }, [open]);
  if (!open) return null;

  const choose = (command?: Command) => { if (!command) return; close(); command.run(); };
  const keydown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") { event.preventDefault(); close(); }
    else if (event.key === "ArrowDown") { event.preventDefault(); setActive(i => Math.min(results.length - 1, i + 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActive(i => Math.max(0, i - 1)); }
    else if (event.key === "Enter") { event.preventDefault(); choose(results[active]); }
    else if (event.key === "Tab") event.preventDefault();   // focus stays in the box: the list is driven by the arrow keys
  };

  return (
    <div className="palette-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) close(); }}>
      <div className="palette" role="dialog" aria-modal="true" aria-label={t("Quick search")} onKeyDown={keydown}>
        <input ref={input} className="inp" role="combobox" aria-expanded="true" aria-controls="palette-list" aria-activedescendant={results[active] ? `palette-${results[active].id}` : undefined} aria-label={t("Search pages, experiments, GPUs and actions")} placeholder={t("Search pages, experiments, GPUs and actions")} value={query} onChange={event => { setQuery(event.target.value); setActive(0); }} autoComplete="off" />
        <ul id="palette-list" role="listbox">
          {results.length === 0 && <li className="palette-empty" role="presentation">{t("Nothing matches")}</li>}
          {results.map((command, index) => (
            <li key={command.id} id={`palette-${command.id}`} role="option" aria-selected={index === active} className={index === active ? "on" : ""} onMouseEnter={() => setActive(index)} onMouseDown={event => { event.preventDefault(); choose(command); }}>
              <span>{command.label}</span><small>{command.hint ?? command.group}</small>
            </li>
          ))}
        </ul>
        <p className="palette-foot hint">↑↓ {t("to move")} · Enter {t("to open")} · Esc {t("to close")}</p>
      </div>
    </div>
  );
}
