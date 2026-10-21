"""Write gsm8k_es_lab.ipynb (cells only, no outputs). Run: .venv-notebook/bin/python runtime/notebooks/build_gsm8k_es_lab.py"""

from pathlib import Path

import nbformat as nbf

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
    md("""# GSM8K on a heterogeneous volunteer GPU lab

**A lab notebook for HeteroES r11.** Four consumer GPUs in three homes, one coordinator, full-weight evolution strategies (ES)
on Qwen2.5-0.5B-Instruct, grade-school math (GSM8K) as the task.

| | |
|---|---|
| Lab | `lab.heteroes.site`, release `93ff85f` (r11) |
| Model | `Qwen/Qwen2.5-0.5B-Instruct` @ `7ae5576`, FP32, all 494M weights trained |
| Data | `openai/gsm8k` @ `740312a`: 6,973 train / 500 validation (both from the official train split) / 1,319 official test |
| Predeclaration | `docs/evidence/2026-10-22-gsm8k-demo/README.md`, committed before any run |

The notebook is organised like an experiment record: **question → claims → method → three tiers of runs → results → what
this does not show.** Every number below is read from the lab's own records of the run; nothing is simulated."""),
    md("""## 1. Question and claims

**Question.** Can a handful of mismatched consumer GPUs, owned by different people and joined over the internet, run
full-parameter ES on a language model with results that are *checkable to the last bit*, while machines are slow,
leave and come back?

We separate two kinds of claims, because they need different evidence:

| | Claim | Evidence in this notebook |
|---|---|---|
| **S1** | Every update can be re-derived exactly from the ledger (seeds + rewards), on another machine | full regeneration (tier 1), ledger replay (tiers 2 and 3) |
| **S2** | Work flows to whoever is free; a fast GPU does more, a slow one is not waited for | per-device work split (all tiers) |
| **S3** | A machine can leave and rejoin a running experiment without breaking it | declared OFF/ON event (tier 2) |
| **S4** | Results computed on one GPU are re-computed identically on another (audits) | audit log (all tiers) |
| **L1** | ES improves GSM8K accuracy of this model | *exploratory only*: one overnight run, one seed (tier 3) |

S1–S4 are the project's claim (a system). L1 is reported, not claimed."""),
    md("""## 2. Setup

The notebook talks to the live lab with the session written by `scripts/lab-login.py` (a 12-hour token in
`~/.config/heteroes-demo/session.json`; no password or token is ever printed here). `heteroes.demo` holds the small client,
a pure *frame builder* (the lab's timeline → what the dashboard draws) and the dashboard itself."""),
    code("""import json
from pathlib import Path
from IPython.display import HTML, Image, Markdown, display

from heteroes.demo import analysis, gsm8k
from heteroes.demo.dashboard import Dashboard, live, render_video
from heteroes.demo.lab import DemoLab, coordinator_events
from heteroes.demo.state import build_frame, replay_frames

lab = DemoLab()
NAMES, EVIDENCE = gsm8k.NAMES, gsm8k.EVIDENCE
rows = []
for d in lab.devices():
    if d["workerId"] in NAMES:
        st = d["selfTest"] or {}
        env = st.get("environment") or {}
        rows.append({"device": NAMES[d["workerId"]], "GPU": st.get("gpuName"), "VRAM (GB)": round((st.get("vramTotalMb") or 0) / 1024, 1),
                     "OS": "Windows" if "Windows" in str(env.get("platform")) else ("WSL2" if "microsoft" in str(env.get("platform")) else "Linux"),
                     "torch": env.get("torch"), "online": d["connectionStatus"]})
rows.append({"device": "3060-thao", "GPU": "NVIDIA GeForce RTX 3060", "VRAM (GB)": 12.0, "OS": "Windows (desktop app)", "torch": "", "online": "(another account's device)"})
display(HTML(analysis.html_table(rows, "Members of the lab (5070ti-nhan is also the coordinator)")))"""),
    md("""## 3. Method: ES in one picture

One **generation**:

1. The coordinator picks one **batch** of GSM8K questions (32 in tiers 2–3). *Every candidate is graded on this same batch.*
2. It defines **N candidates**. Candidate *i* is the current model θ plus Gaussian noise σ·εᵢ, where εᵢ is regenerated
   from a seed (so only the seed travels, never the 2 GB of noise).
3. Each candidate is one unit of work. Any free GPU takes one, answers all questions of the batch, and returns the
   **reward**: the share of questions it got right (the last number of the answer equals the reference).
4. Rewards are z-scored against the population (zᵢ = (rᵢ − mean)/std), and the model moves toward the noise of the
   good candidates:

$$\\theta \\leftarrow \\theta + \\frac{\\alpha}{N}\\sum_{i=1}^{N} z_i\\,\\varepsilon_i$$

Because the update needs only (seedᵢ, rewardᵢ), anyone holding the ledger can recompute θ exactly. That is the basis of S1.

**How work is split (S2).** Devices do not split the *questions*, they split the *candidates*. A faster GPU asks for work
more often, so it simply finishes more candidates (scheduler `greedy-tail`, which also avoids handing the last candidates of
a generation to a slow device). **Current limit:** the number of questions decoded together (`evalChunk` = 32) is fixed in
the recipe for every device, because a different batch shape can flip one token in about 1 of 768 long answers and break
bit-exact audits. So extra VRAM buys nothing yet (backlog item 9).

**Near-ties.** Long answers sometimes reach a step where the two best tokens differ by less than 0.01 in score; different
GPUs may then pick differently. The decoder `hf_fp32_cpu_guard_v1` recomputes exactly those steps on the CPU in FP64, so
every GPU picks the same token (numerical contract §17.1)."""),
    md("""### Recipe, next to the reference papers

| | ES at Scale (Qiu et al.) | Understanding ES (Ba et al.) | **This run (tier 3)** |
|---|---|---|---|
| Model | Qwen2.5-1.5B / 3B | Qwen2.5-0.5B / 1.5B / 3B-Instruct | **Qwen2.5-0.5B-Instruct** |
| Population N | 30 (16–128 ablated) | 32 (8–64 ablated; 0.5B needs ≥ 32) | **32** |
| Batch / data order | fixed 512 prompts | 64, shuffled epochs | **32, shuffled epochs** (`epoch-shuffle@1`) |
| Updates | 300 | ~234 (2 epochs) | **300** |
| σ | 1e-3 (ablated) | 1.5e-3 | **cosine 1e-3 → 2.5e-4** (as Agentic ESOpt) |
| α | σ/2 | 2.5e-4 | **5e-4** |
| Normalisation | z-score | z-score (better than none) | **z-score** |
| Hardware | datacenter GPUs | datacenter GPUs | **5070 Ti + 2× 3060 + 1660 SUPER, three homes** |"""),
    md("""## 4. Tier 1: smoke (2 generations, N = 8, batch 8)

The first managed run of the r11 lab. `gsm8k.launch` is idempotent: running this cell again returns the same experiment.
`live` redraws the dashboard until the run ends (for a finished run, it shows the final state at once). Audits and
validations are read from the coordinator's own event log on this machine (the lab-wide event feed is slow to poll)."""),
    code("""tier1 = gsm8k.launch(lab, "tier1")
frame1 = live(lab, tier1["experimentId"], NAMES, coordinator="5070ti-nhan", every=3, events=coordinator_events(tier1["experimentId"]))"""),
    code("""t1 = json.loads((EVIDENCE / "tier1" / "timeline.json").read_text())
e1 = json.loads((EVIDENCE / "tier1" / "events.json").read_text())
x1 = json.loads((EVIDENCE / "tier1" / "experiment.json").read_text())
display(HTML(analysis.html_table(analysis.work_split(t1, NAMES), "Committed candidates per device and generation")))
display(HTML(analysis.html_table(analysis.device_totals(t1, NAMES), "Per device")))
display(HTML(analysis.html_table(analysis.audits(e1, NAMES), "Audits: a second device re-ran a candidate and compared the texts")))
m = x1["studyMetrics"]
display(Markdown(f\"\"\"**Validation (64 rows):** base {m['validation'][0]['meanReward']:.3f} → after 2 generations {m['best']['validationReward']:.3f}.
**Test (64 rows, once, on the selected checkpoint):** {m['testReward']:.3f}; independent reload passed: {m['independentReloadPassed']}.\"\"\"))"""),
    code("""p1 = json.loads((EVIDENCE / "tier1" / "parity.json").read_text())
display(Markdown(f\"\"\"**S1, full regeneration on the 5070 Ti:** {'ALL EQUAL' if p1['allEqual'] else 'DIFFERENCES'}:
{sum(len(g['candidates']) for g in p1['generations'])} candidates re-generated from the recipe, the dataset and the seeds alone;
texts, rewards, generation records and both child-weight hashes equal to the distributed run's
(`{p1['generations'][-1]['childSha256'][:16]}…`).\"\"\"))"""),
    md("""**Finding in tier 1 (product).** `3060-thao` was meant to join over the *public* compute route with its VPN (Tailscale)
switched off. It never started: the public route is replay-only by design, and the agent refuses to fetch *any* dataset
file over a public URL (`study/prepare.py`). So a device without a private route cannot take part in a dataset run at all.
Tailscale was switched back on for tiers 2 and 3 (recorded in `RESULTS.md`)."""),
    md("""## 5. Tier 2: the system under stress (5 generations, N = 32, batch 32)

Same recipe as the overnight run, shorter. Four moments are staged and checked (predeclared):

* **(a) uneven work:** the per-device table below;
* **(b) leave and rejoin:** `quang-3060` is switched **OFF** once generation 3 opens (index 2) and **ON** once generation 4
  opens (index 3), by the owner's own switch, exactly what the web button does (`lab.set_contribution`);
* **(c) audits:** about 5% of candidates are re-run by another device;
* **(d) parity:** the ledger replay re-derives every update, and one whole generation is regenerated."""),
    code("""tier2 = gsm8k.launch(lab, "tier2")
frame2 = live(lab, tier2["experimentId"], NAMES, coordinator="5070ti-nhan", every=3, events=coordinator_events(tier2["experimentId"]))"""),
    code("""# The declared events were performed by stage_events.py (the same calls as below) while the run was live:
#   lab.set_contribution("cli-73b87e369ddc", False)  when generation index 2 opened
#   lab.set_contribution("cli-73b87e369ddc", True)   when generation index 3 opened
for line in (EVIDENCE / "tier2" / "stage-events.jsonl").read_text().splitlines():
    entry = json.loads(line); entry.pop("response", None); print(entry)
t2 = json.loads((EVIDENCE / "tier2" / "timeline.json").read_text())
e2 = json.loads((EVIDENCE / "tier2" / "events.json").read_text())
display(HTML(analysis.html_table(analysis.work_split(t2, NAMES), "Committed candidates per device and generation")))
display(HTML(analysis.html_table(analysis.device_totals(t2, NAMES), "Per device")))
display(HTML(analysis.html_table(analysis.membership(t2, NAMES), "Membership changes seen by the coordinator")))
display(HTML(analysis.html_table(analysis.audits(e2, NAMES), "Audits")))"""),
    code("""p2 = json.loads((EVIDENCE / "tier2" / "parity.json").read_text())
display(Markdown(f\"\"\"**S1 for tier 2:** {'ALL EQUAL' if p2['allEqual'] else 'DIFFERENCES'}; every one of the
{len(p2['generations'])} updates re-derived from the ledger (child hashes equal), generation(s) {[g + 1 for g in p2['regenerated']]}
fully regenerated (texts and rewards equal).\"\"\"))
Dashboard("5070ti-nhan").save(build_frame(t2, e2, NAMES), "/tmp/tier2-final.png")
display(Image("/tmp/tier2-final.png"))"""),
    md("""## 6. Tier 3: overnight (300 generations, N = 32, batch 32, cosine σ)

Launched only after tiers 1 and 2 passed. Validation (500 held-out rows) every 25 generations; the lab keeps the best
checkpoint by validation and evaluates it **once** on the 1,319 test rows at the end. The cell below attaches to the run
at any moment: run it again to see where the night is."""),
    code("""run3 = gsm8k.run_id("tier3")
if run3 is None:
    display(Markdown("*Tier 3 has not been launched (it needs tiers 1 and 2 to pass).*"))
else:
    frame3 = live(lab, run3, NAMES, coordinator="5070ti-nhan", every=10, until=lambda f: True, events=coordinator_events(run3))  # one snapshot; drop `until` to follow"""),
    code("""results3 = EVIDENCE / "tier3" / "experiment.json"
if results3.exists():
    x3 = json.loads(results3.read_text()); m3 = x3.get("studyMetrics") or {}
    t3 = json.loads((EVIDENCE / "tier3" / "timeline.json").read_text())
    display(HTML(analysis.html_table(analysis.device_totals(t3, NAMES), "Per device, whole night")))
    display(HTML(analysis.html_table([{"generation": v["generation"] + 1, "validation reward": round(v["meanReward"], 4)} for v in m3.get("validation", [])],
                                     "Validation (500 rows) every 25 generations; generation 0 = base")))
    display(Markdown((EVIDENCE / "tier3" / "summary.md").read_text() if (EVIDENCE / "tier3" / "summary.md").exists() else "*Summary pending.*"))
else:
    display(Markdown("*Tier 3 results are written when the run ends.*"))"""),
    md("""## 7. Replay

The same frames, as a video (`media/`) and as a self-contained web page that replays the run in a browser, phone included
(`heteroes.demo.replay_page`)."""),
    code("""media = EVIDENCE / "media"
for name in ("tier2.mp4", "tier3.mp4"):
    if (media / name).exists():
        from IPython.display import Video
        display(Markdown(f"**{name}**")); display(Video(str(media / name), embed=True, width=900))"""),
    md("""## 8. What this does NOT show

* **Not a learning result.** One seed, one overnight run of a 0.5B model; the reference papers use larger models, other data
  orders and several seeds. A change in GSM8K accuracy smaller than about ±2.7 points (1,319 test rows) is inside sampling noise.
* **Not universal bit-equality.** Audits and regeneration matched on these four GPUs, these drivers and this decoder; the
  near-tie guard's 0.01 threshold is empirical.
* **Not the public route.** The device without a private network could not join (tier 1 finding).
* **Not per-device batch sizes:** every device decodes 32 questions at a time (backlog item 9).
* **No coordinator or lab crash** was staged here (earlier evidence covers member restarts)."""),
]

notebook = nbf.v4.new_notebook(cells=cells)
notebook.metadata["kernelspec"] = {"name": "heteroes-notebook", "display_name": "HeteroES notebook", "language": "python"}
nbf.write(notebook, Path(__file__).with_name("gsm8k_es_lab.ipynb"))
