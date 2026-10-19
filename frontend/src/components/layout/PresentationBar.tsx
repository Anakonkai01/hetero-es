import { useProduct } from "@heteroes/product-ui";
import { useEffect } from "react";
import { useLocation,useNavigate } from "react-router";
import { usePresentation } from "../../app/presentationContext";
import { useExperiments } from "../../hooks/useExperiments";
import { presentationScenes } from "../../lib/presentationScenes";

/** While presenting: scene buttons at the bottom, left/right arrows to move between scenes, Escape to leave. */
export function PresentationBar() {
  const { t } = useProduct();
  const { on, set } = usePresentation();
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  const experiments = useExperiments();
  const scenes = presentationScenes(experiments.data ?? []);
  const current = scenes.findIndex(scene => scene.to === pathname + search);

  useEffect(() => {
    if (!on) return;
    const key = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
      if (event.key === "Escape") set(false);
      if (!scenes.length || (event.key !== "ArrowRight" && event.key !== "ArrowLeft")) return;
      // Where we are is read at the moment of the key press: a quick second press must not use the previous render's position.
      const here = scenes.findIndex(scene => scene.to === location.pathname + location.search);
      const next = event.key === "ArrowRight" ? Math.min(scenes.length - 1, here + 1) : Math.max(0, here - 1);
      if (next !== here) navigate(scenes[next].to);
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [on, set, scenes, navigate]);

  if (!on) return null;
  return (
    <div className="presentation-bar" role="region" aria-label={t("Presentation")}>
      <span className="hint">{t("Arrow keys change the scene")}</span>
      {scenes.map((scene, index) => <button key={scene.to} type="button" className={index === current ? "btn pri" : "btn"} aria-current={index === current ? "page" : undefined} onClick={() => navigate(scene.to)}>{index + 1} · {t(scene.label)}</button>)}
      <button type="button" className="btn" onClick={() => set(false)}>{t("Exit presentation")}</button>
    </div>
  );
}
