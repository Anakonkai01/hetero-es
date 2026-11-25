"""Write the experiment notebooks (cells only, no outputs), in Vietnamese like ../demo.ipynb:

e1-gsm8k-qwen05, e2-arith-smollm2, e3-gsm8k-qwen15, e4-countdown-qwen15 and tong-hop (the summary).

Run: python runtime/notebooks/experiments/build_experiments.py   (any Python with nbformat)
"""

from pathlib import Path

import nbformat as nbf

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
HERE = Path(__file__).resolve().parent

PAPER = "tham số của Qiu et al. 2025 (ES cho LLM): σ = 0,001, α = 5·10⁻⁴, khoảng 30 candidate"

EXPERIMENTS = {
    "e1-gsm8k-qwen05": {
        "title": "GSM8K × Qwen2.5-0.5B-Instruct",
        "task": "gsm8k",
        "about": "Bài toán lời văn cấp tiểu học (GSM8K, bộ chuẩn công khai): mô hình giải từng bước rồi ghi con số cuối "
        "trong `\\boxed{}`. Đây là bài toán thứ ba của đề tài, sau phép nhân và Countdown.",
        "repo": "Qwen/Qwen2.5-0.5B-Instruct",
        "revision": "7ae557604adf67be50417f59c2c2f167def9a775",
        "tokens": 320,
        "reward": "boxed",
        "first": {"alpha": 5e-4, "sigma": 1e-3, "generations": 100, "reason": PAPER},
        "validation": 20,
    },
    "e2-arith-smollm2": {
        "title": "Phép nhân × SmolLM2-360M-Instruct (họ Llama)",
        "task": "arithmetic",
        "about": "Cùng bài phép nhân của notebook demo nhưng với một **họ mô hình khác**: SmolLM2 dùng kiến trúc Llama, "
        "không phải Qwen. Bộ suy luận nghiêm ngặt của HeteroES hỗ trợ Qwen2, Llama và Mistral. Mô hình gốc hay ghi cả "
        "phép tính vào `\\boxed{}` (ví dụ `\\boxed{879 * 2} = 1758`), nên bộ chấm có sẵn cho 0 điểm gần như mọi câu "
        "và ES không có tín hiệu để học. Notebook này dùng một **hàm reward Python tự viết** có điểm từng phần.",
        "repo": "HuggingFaceTB/SmolLM2-360M-Instruct",
        "revision": "a10cc1512eabd3dde888204e902eca88bddb4951",
        "tokens": 24,
        "reward": "shaped",
        "first": {"alpha": 5e-4, "sigma": 1e-3, "generations": 60, "reason": PAPER},
        "validation": 10,
    },
    "e3-gsm8k-qwen15": {
        "title": "GSM8K × Qwen2.5-1.5B-Instruct",
        "task": "gsm8k",
        "about": "GSM8K với mô hình lớn gấp ba (1,5 tỉ tham số). Mỗi candidate là một bản sao 1,5B tham số cộng nhiễu, "
        "nên đây là phép thử tải của hệ thống trên GPU 12 GB.",
        "repo": "Qwen/Qwen2.5-1.5B-Instruct",
        "revision": "989aa7980e4cf806f80c7fef2b1adb7bc71aa306",
        "tokens": 320,
        "reward": "boxed",
        "first": {"alpha": 5e-4, "sigma": 1e-3, "generations": 100, "reason": PAPER},
        "validation": 20,
    },
    "e4-countdown-qwen15": {
        "exclude": ["1660s"],  # GTX 1660S is sm75: the strict decoder needs sm80 (GPU_UNSUPPORTED_BY_DECODER)
        "title": "Countdown × Qwen2.5-1.5B-Instruct",
        "task": "countdown",
        "about": "Countdown (dùng các số cho trước và + − × ÷ để ra số đích) với mô hình 1,5B, cùng dữ liệu và cách chia "
        "của run Countdown 0,5B trong báo cáo, để so sánh hai cỡ mô hình.",
        "repo": "Qwen/Qwen2.5-1.5B-Instruct",
        "revision": "989aa7980e4cf806f80c7fef2b1adb7bc71aa306",
        "tokens": 384,
        "reward": "countdown",
        "first": {"alpha": 5e-4, "sigma": 1e-3, "generations": 150, "reason": PAPER},
        "validation": 25,
    },
}

SETUP = r'''import json
import sys
import time
from pathlib import Path

HERE = Path.cwd()
SRC = (HERE / ".." / ".." / "src").resolve()  # runtime/notebooks/experiments -> runtime/src
for path in (str(SRC), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

import runner  # noqa: E402  (sets a clean Hugging Face cache first)
import tasks  # noqa: E402
from heteroes.sdk import ESConfig, ESTrainer, reward  # noqa: E402
from heteroes.sdk_lab import Dataset, Lab, Model  # noqa: E402

NAME = {name!r}
CHAY_MOI = False  # True: a short new run for a live demo (a few generations) instead of re-attaching to the recorded one
COORDINATOR = {coordinator!r}  # the coordinator goes to a GPU (owner rule)
EXCLUDE = {exclude!r}  # names of devices to leave out of a new segment

experiment = runner.Experiment(NAME + (time.strftime("-demo-%Y%m%d-%H%M") if CHAY_MOI else ""))
lab = Lab.from_session()  # python3 scripts/lab-login.py signs in once (12 hours)


def online_workers():
    return [d.name for d in lab.devices() if d.online and d.on and not d.cpu_only and d.name not in EXCLUDE]


for d in lab.devices():
    print(f"{{d.name:16}} {{d.gpu:28}} {{d.vram_gb:5.1f}} GB  online={{d.online}} ON={{d.on}} bận={{d.busy}}")'''

DATA = {
    "gsm8k": r'''splits = tasks.gsm8k()  # train less 500 seeded rows = validation; official test = test
data = Dataset.from_rows(**splits, directory=experiment.dir / "data")
print({k: len(v) for k, v in splits.items()}, "| mã băm dữ liệu", data.sha256[:16], "…")
print(splits["test"][0]["prompt"], "\n→ đáp án", splits["test"][0]["answer"])''',
    "arithmetic": r'''from heteroes.v3 import data as v3data

splits = v3data.build(tasks.arithmetic(), split_seed=42)["splits"]  # the same seeded 80/10/10 split as the demo
splits = {k: [dict(r) for r in v] for k, v in splits.items()}
data = Dataset.from_rows(**splits, directory=experiment.dir / "data")
print({k: len(v) for k, v in splits.items()}, "| mã băm dữ liệu", data.sha256[:16], "…")
print(splits["test"][0]["prompt"], "→ đáp án", splits["test"][0]["answer"])''',
    "countdown": r'''from heteroes.v3 import data as v3data

splits = v3data.build(tasks.countdown(), split_seed=42)["splits"]  # the split of the 0.5B Countdown run
splits = {k: [dict(r) for r in v] for k, v in splits.items()}
data = Dataset.from_rows(**splits, directory=experiment.dir / "data")
print({k: len(v) for k, v in splits.items()}, "| mã băm dữ liệu", data.sha256[:16], "…")
print(splits["test"][0]["prompt"], "→ số đích", splits["test"][0]["target"])''',
}

REWARD = {
    "boxed": r'''SCORER = {"name": "boxed-number", "config": {"answerField": "answer", "formatReward": 0.1}}
TEST_SCORER = SCORER  # "đúng" = score 1: the boxed number equals the answer
make_reward = dict(scorer=SCORER)''',
    "countdown": r'''SCORER = {"name": "countdown", "config": {"numbersField": "nums", "targetField": "target"}}
TEST_SCORER = SCORER  # "đúng" = score 1: a valid expression over the given numbers that equals the target
make_reward = dict(scorer=SCORER)''',
    "shaped": r'''@reward("arith-shaped@1")
def arith_shaped(completions, rows):
    """1 when the boxed number is the answer, 0.5 when the answer appears elsewhere, 0.1 for a box, else 0."""
    import re

    out = []
    for text, row in zip(completions, rows):
        boxed = re.findall(r"\\boxed\{([^{}]*)\}", text)
        if boxed and boxed[-1].strip().replace(",", "") == row["answer"]:
            out.append(1.0)
        elif re.search(r"(?<![\d.])" + re.escape(row["answer"]) + r"(?![\d.])", text):
            out.append(0.5)
        elif boxed:
            out.append(0.1)
        else:
            out.append(0.0)
    return out


TEST_SCORER = {"name": "boxed-number", "config": {"answerField": "answer", "formatReward": 0.1}}  # strict on test
make_reward = dict(reward_func=arith_shaped)
demo = splits["test"][0]
texts = [f"\\boxed{{{demo['answer']}}}", f"\\boxed{{1 * 2}} = {demo['answer']}", "\\boxed{7}", "không biết"]
print(list(zip(texts, arith_shaped(texts, [demo] * len(texts)))))''',
}


def notebook(name, e):
    tokens = e["tokens"]
    cells = [
        md(f"""# Thí nghiệm {name.split('-')[0].upper()}: {e['title']}

{e['about']}

Notebook chạy theo đúng luồng của người nghiên cứu trên lab HeteroES:

| Bước | Ở đây |
|---|---|
| Mô hình | `Model.from_hf` ghim một commit Hugging Face; **mỗi máy tự tải từ Hugging Face** và kiểm SHA-256 từng tệp |
| Dữ liệu | `Dataset.from_rows` (train / validation / test cố định, ghim mã băm) |
| Chạy | `ESTrainer.submit(lab, coordinator, workers)`: lab xếp hàng, chia candidate cho các GPU, chấm chéo (audit) |
| Nối tiếp | mỗi đoạn sau bắt đầu từ trọng số cuối đã kiểm chứng của đoạn trước (`derive_model`) |
| Đánh giá | chọn checkpoint bằng validation; tập test chỉ chấm **một lần** ở cuối, kiểm định McNemar |

Các đoạn và lý do chọn tham số nằm ở `decisions/{name}.json`; mã thí nghiệm trên lab ở `state/{name}.json`. Chạy lại
notebook sẽ gắn vào các run đã có (không chạy lại). Đặt `CHAY_MOI = True` để chạy một run ngắn mới khi demo."""),
        md("## 1. Chuẩn bị: kết nối lab và xem các GPU"),
        code(SETUP.format(name=name, coordinator=e.get("coordinator", "5070ti-nhan"),
                          exclude=set(e.get("exclude", ())) or set())),
        md("## 2. Dữ liệu"),
        code(DATA[e["task"]]),
        md(f"""## 3. Mô hình

`{e['repo']}` được ghim theo commit `{e['revision'][:12]}…`. Trên lab đây là mô hình **tham chiếu**: lab không giữ bản
sao, mỗi worker tự tải từ Hugging Face rồi kiểm tra mã băm từng tệp trước khi làm việc."""),
        code(f'''model = Model.from_hf({e['repo']!r}, revision={e['revision']!r})
print(model.id, model.revision[:12], model.source)
for file, sha in model.manifest["files"].items():
    print(f"  {{file:28}} {{sha[:16]}}…")'''),
        md(f"""## 4. Reward

Reward của một candidate là trung bình điểm trên lô 32 câu train. Trên tập test, **"đúng" nghĩa là điểm 1** (đáp án
chính xác)."""),
        code(REWARD[e["reward"]]),
        md(f"""### Mô hình gốc trả lời thế nào?

Ba câu test đầu, giải mã tham lam bằng bộ suy luận nghiêm ngặt `strict_b22_v1` như trong thí nghiệm (tối đa {tokens}
token)."""),
        code(f'''sample = splits["test"][:3]
before = runner.score_model(model.path, sample, TEST_SCORER, {tokens})
for row, text, s in zip(sample, before["outputs"], before["scores"]):
    print(f"[điểm {{s}}]", repr(text[-300:]))'''),
        md(f"""## 5. Cấu hình

32 candidate mỗi thế hệ, mỗi candidate chấm trên 32 câu train; σ và α theo từng đoạn. Validation
({'500 câu' if e['task'] == 'gsm8k' else 'tập validation'}) được chấm mỗi {e['validation']} thế hệ trên coordinator."""),
        code(f'''def make_trainer(model, segment):
    args = ESConfig(
        model=model,
        dataset=data,
        population=32,
        batch_size=32,
        generations=3 if CHAY_MOI else segment["generations"],
        alpha=segment["alpha"],
        sigma=segment["sigma"],
        max_new_tokens={tokens},
        eval_dtype="float16",
        decoder="strict_b22_v1",  # same tokens on every supported NVIDIA GPU
        eval_chunk=32,
        validation_interval={e['validation']},
        audit_rate=0.05,
    )
    return ESTrainer(args, code_dir=experiment.dir / "code", **make_reward)


segments = experiment.segments({e['first']!r})
for i, s in enumerate(segments, 1):
    print(f"đoạn {{i}}: α={{s['alpha']}} σ={{s['sigma']}} {{s['generations']}} thế hệ — {{s['reason']}}")'''),
        md("""## 6. Chạy trên lab

Mỗi đoạn là một experiment trên lab. Ô này chờ đến khi các đoạn xong (xem trực tiếp trên trang Experiments của lab);
khi chạy lại notebook, các đoạn đã có chỉ được gắn lại."""),
        code('''runs = runner.run_segments(lab, experiment, model, make_trainer, segments, COORDINATOR, online_workers)
for (segment, run, _), i in zip(runs, range(1, len(runs) + 1)):
    print(f"đoạn {i}: {run.id} {run.status()} {run.url}")'''),
        md("## 7. Quá trình học"),
        code('''import matplotlib.pyplot as plt

rewards, validation, work = runner.history(runs)
fig, (a, b) = plt.subplots(1, 2, figsize=(12, 3.4), gridspec_kw={"width_ratios": [3, 1]})
a.plot([g for g, _ in rewards], [r for _, r in rewards], color="#9db8d8", lw=1, label="reward lô train")
a.plot([g for g, _ in validation], [r for _, r in validation], "o-", color="#c2410c", label="reward validation")
for end in [sum(s["generations"] for s, _, _ in runs[:k]) for k in range(1, len(runs))]:
    a.axvline(end - 0.5, color="#999", ls=":", lw=1)
a.set_xlabel("thế hệ")
a.set_ylabel("reward")
a.legend()
names = {d.worker_id: d.name for d in lab.devices()}
b.barh([names.get(w, w) for w in work], list(work.values()), color="#2a78d6")
b.set_xlabel("candidate đã chấm")
plt.tight_layout()
plt.show()
print("validation:", [(g, round(r, 4)) for g, r in validation])'''),
        md("""## 8. Chọn checkpoint và chấm test (một lần)

Checkpoint được chọn là cuối đoạn có reward validation cao nhất. Tập test được chấm cho mô hình gốc, cuối đoạn đầu và
checkpoint được chọn; kết quả lưu lại nên chạy lại notebook không chấm lại."""),
        code(f'''ends = []
for k, (segment, run, _) in enumerate(runs, 1):
    marks = [v for v in run.results()["validation"] if v["generation"] is not None]
    ends.append((marks[-1]["reward"], k))
best = max(ends)[1]
print("validation cuối mỗi đoạn:", ends, "→ chọn đoạn", best)

done = [(s, r, m) for s, r, m in runs]
first_dir = runner.after_segment(lab, experiment, done, 1).path
best_dir = runner.after_segment(lab, experiment, done, best).path
rows = splits["test"]
base = runner.test_report(experiment, "base", -1, model.path, rows, TEST_SCORER, {tokens})
first = runner.test_report(experiment, "first", 1, first_dir, rows, TEST_SCORER, {tokens})
chosen = runner.test_report(experiment, f"segment-{{best:02d}}", best, best_dir, rows, TEST_SCORER, {tokens})
for label, report in (("mô hình gốc", base), ("cuối đoạn 1", first), (f"chọn (đoạn {{best}})", chosen)):
    ok, n = runner.correct(report)
    print(f"{{label:16}} đúng {{ok}}/{{n}} = {{ok / n:6.1%}}   reward {{report['checkpoints'][0]['meanReward']:.4f}}")'''),
        code('''from heteroes.v3.comparison import compare

result = compare(base, chosen)
print(f"gốc → chọn: sửa đúng {result['fixed']}, làm sai {result['broke']}, McNemar p = {result['mcnemarExactP']:.2g}, "
      f"khoảng tin cậy 95% của mức tăng reward [{result['bootstrapCI'][0]:.3f}; {result['bootstrapCI'][1]:.3f}]")
if best != 1:
    later = compare(first, chosen)
    print(f"đoạn 1 → chọn: sửa {later['fixed']}, làm sai {later['broke']}, p = {later['mcnemarExactP']:.2g}")'''),
        md("## 9. Ví dụ trước / sau"),
        code('''shown = 0
for i, row in enumerate(rows):
    a, b = base["checkpoints"][0], chosen["checkpoints"][0]
    if a["scores"][i] != 1 and b["scores"][i] == 1:
        print("—", row["prompt"][:200].replace("\\n", " "))
        print("  gốc :", repr(a["outputs"][i][-200:]))
        print("  sau :", repr(b["outputs"][i][-200:]))
        shown += 1
    if shown == 3:
        break'''),
        md("## 10. Lưu tóm tắt (cho notebook tổng hợp)"),
        code('''summary = {
    "name": NAME, "model": model.id, "revision": model.revision, "segments": [{**s, "experimentId": r.id} for s, r, _ in runs],
    "validation": validation, "workPerDevice": {names.get(w, w): c for w, c in work.items()},
    "test": {label: dict(zip(("correct", "count"), runner.correct(rep))) | {"meanReward": rep["checkpoints"][0]["meanReward"]}
             for label, rep in (("base", base), ("first", first), ("selected", chosen))},
    "selectedSegment": best, "comparison": result,
}
out = runner.HERE / "results" / f"{experiment.name}.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\\n")
print("đã lưu", out)'''),
    ]
    return cells


SUMMARY = [
    md("""# Tổng hợp các thí nghiệm HeteroES (đêm 24 → 25/11/2026)

Bảng gom kết quả các notebook thí nghiệm (`results/*.json`). "Đúng" = điểm 1 trên tập test, chấm **một lần** ở cuối;
p là kiểm định McNemar chính xác (mô hình gốc so với checkpoint được chọn). Run Countdown × Qwen2.5-0.5B có từ trước
(test 0 → 32/249) nằm trong báo cáo, không lặp lại ở đây."""),
    code(r'''import json
from pathlib import Path

HERE = Path.cwd()
print(f"{'mô hình':30} {'thí nghiệm':22} {'n':>5} {'gốc':>5} {'sau ES':>7} {'p':>9}  thế hệ")
for path in sorted((HERE / "results").glob("*.json")):
    s = json.loads(path.read_text())
    t = s["test"]
    state = json.loads((HERE / "state" / path.name).read_text())["segments"]
    planned = sum(x["generations"] for x in s["segments"])
    early = [v["endedEarly"] for v in state.values() if v.get("endedEarly")]
    note = f"{planned} (dừng sớm: {early[0]})" if early else str(planned)
    print(f"{s['model']:30} {s['name']:22} {t['base']['count']:5} {t['base']['correct']:5} "
          f"{t['selected']['correct']:7} {s['comparison']['mcnemarExactP']:9.2g}  {note}")'''),
    md("""## Tốc độ trong run thật: 1 GPU so với 2 GPU

Đọc từ ledger của coordinator (máy 5070 Ti của Nhân), nơi ghi **mọi** candidate: máy nào chấm, lúc nào xong.
Thời gian một thế hệ = khoảng cách giữa hai lần ghi cập nhật trọng số (gồm cả các lần chấm validation mỗi 25 thế hệ,
nên dùng trung vị). Audit = một máy khác chấm lại một candidate; phải ra cùng SHA-256 của câu trả lời."""),
    code(r'''import collections
import sqlite3
import statistics

RUNS = Path.home() / ".local/share/heteroes-worker/agent-state/runs"
NAMES = {"cli-3dacd1745773": "5070ti-nhan", "cli-d152aa6a13f8": "5070ti-nhut", "cli-1a9e23ce56d1": "3060-quang",
         "cli-a6c1c55a80d8": "3060-thao"}


def speed(run_id):
    db = sqlite3.connect(f"file:{RUNS / run_id / 'ledger.sqlite'}?mode=ro", uri=True)
    done = dict(db.execute("SELECT generation, recorded_at FROM generation_update"))
    who = collections.defaultdict(set)
    for g, w in db.execute(
        "SELECT c.generation, a.worker_id FROM result r JOIN attempt a ON a.candidate_id = r.candidate_id "
        "AND a.attempt_number = r.attempt_number JOIN candidate c ON c.candidate_id = r.candidate_id"
    ):
        who[g].add(NAMES.get(w, w))
    groups = collections.defaultdict(list)
    for g in sorted(done):
        if g - 1 in done and who.get(g):
            groups[" + ".join(sorted(who[g]))].append(done[g] - done[g - 1])
    audits, matched = db.execute("SELECT COUNT(*), COALESCE(SUM(matched), 0) FROM audit").fetchone()
    return groups, audits, matched


for name in ("e3-gsm8k-qwen15", "e4-countdown-qwen15"):
    run_id = json.loads((HERE / "state" / f"{name}.json").read_text())["segments"]["segment-01"]["experimentId"]
    if not (RUNS / run_id / "ledger.sqlite").is_file():
        print(name, ": ledger không có trên máy này")
        continue
    groups, audits, matched = speed(run_id)
    print(f"{name}: audit khớp {matched}/{audits}")
    for machines, seconds in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f"   {machines:28} {len(seconds):4} thế hệ, trung vị {statistics.median(seconds):6.1f} s/thế hệ")'''),
    md("""Đọc kết quả: E4 chạy 4 thế hệ trên một 5070 Ti rồi máy 5070 Ti thứ hai (của Nhựt) được thêm vào **giữa run**
(không dừng run). Mốc một máy chỉ có 4 thế hệ, gồm cả lúc nạp mô hình, nên tỷ lệ tăng tốc chỉ là ước lượng.
Máy 3060 của Thảo được thêm vào E4 nhưng không gửi được kết quả về coordinator (mạng WSL rớt gói lớn), nên không có
trong bảng; máy 3060 của Quang chỉ tham gia 2 thế hệ đầu của E3 trước khi ổ C: đầy."""),
]

if __name__ == "__main__":
    import sys

    wanted = set(sys.argv[1:])  # e.g. `build_experiments.py e3-gsm8k-qwen15`: rewrite only those (keeps others' outputs)
    for name, spec in EXPERIMENTS.items():
        if wanted and name not in wanted:
            continue
        nb = nbf.v4.new_notebook(cells=notebook(name, spec))
        nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
        (HERE / f"{name}.ipynb").write_text(nbf.writes(nb), encoding="utf-8")
    if not wanted or "tong-hop" in wanted:
        nb = nbf.v4.new_notebook(cells=SUMMARY)
        nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
        (HERE / "tong-hop.ipynb").write_text(nbf.writes(nb), encoding="utf-8")
    print("wrote", sys.argv[1:] or "all notebooks")
