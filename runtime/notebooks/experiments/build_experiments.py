"""Write the experiment notebooks (cells only, no outputs), in Vietnamese like ../demo.ipynb:

00-chuan-bi (lab and GPU machines), e1-gsm8k-qwen05, e3-gsm8k-qwen15, e4-countdown-qwen15,
e5-countdown-qwen05 and tong-hop (the summary). The first round (24-25/11) is kept in v1/.

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
        "trong `\\boxed{}`. Lần 1 (đêm 24/11) dùng giới hạn 320 token: mô hình gốc chưa viết xong khoảng một phần ba số câu, nên mức tăng phần lớn là do mô hình học viết gọn lại cho kịp ghi đáp án. Lần này giới hạn là 512 token (mô hình gốc trả lời xong khoảng 96–98% số câu), và notebook báo thêm tỉ lệ đúng **trên các câu đã trả lời xong**.",
        "repo": "Qwen/Qwen2.5-0.5B-Instruct",
        "revision": "7ae557604adf67be50417f59c2c2f167def9a775",
        "tokens": 512,
        "reward": "boxed",
        "first": {"alpha": 5e-4, "sigma": 1e-3, "generations": 100, "reason": PAPER},
        "validation": 20,
    },
    "e2-gsm8k-llama32-1b": {
        "exclude": ["1660s"],
        "title": "GSM8K × Llama-3.2-1B-Instruct",
        "task": "gsm8k",
        "about": "GSM8K với một họ mô hình khác Qwen: Llama 3.2 (1,2 tỉ tham số, GQA 32/8 đầu, RoPE kiểu `llama3`). "
        "Thí nghiệm này chủ yếu để chứng minh bộ suy luận nghiêm ngặt và lab không gắn với một họ mô hình: từ 25/11 decoder tính "
        "được tần số RoPE `llama3` (kiểm trên CPU so với `transformers`), và lab tự kiểm thử (qualify) mô hình mới trên từng "
        "GPU trước khi chạy. Mô hình gốc đúng khoảng 28% trên 32 câu validation thử, không câu nào bị cắt ở 512 token, nên "
        "mức tăng (nếu có) không phải do viết gọn.",
        "repo": "unsloth/Llama-3.2-1B-Instruct",
        "revision": "5a8abab4a5d6f164389b1079fb721cfab8d7126c",
        "tokens": 512,
        "reward": "boxed",
        "first": {"alpha": 5e-4, "sigma": 1e-3, "generations": 100, "reason": PAPER},
        "validation": 20,
    },
    "e3-gsm8k-qwen15": {
        "title": "GSM8K × Qwen2.5-1.5B-Instruct",
        "task": "gsm8k",
        "about": "GSM8K với mô hình lớn gấp ba (1,5 tỉ tham số). Mỗi candidate là một bản sao 1,5B tham số cộng nhiễu, "
        "nên đây cũng là phép thử tải của hệ thống trên GPU 12 GB. Lần 1 (đêm 24/11) dùng giới hạn 320 token: mô hình gốc chưa viết xong khoảng một phần ba số câu, nên mức tăng phần lớn là do mô hình học viết gọn lại cho kịp ghi đáp án. Lần này giới hạn là 512 token (mô hình gốc trả lời xong khoảng 96–98% số câu), và notebook báo thêm tỉ lệ đúng **trên các câu đã trả lời xong**.",
        "repo": "Qwen/Qwen2.5-1.5B-Instruct",
        "revision": "989aa7980e4cf806f80c7fef2b1adb7bc71aa306",
        "tokens": 512,
        "reward": "boxed",
        "first": {"alpha": 5e-4, "sigma": 1e-3, "generations": 100, "reason": PAPER},
        "validation": 20,
    },
    "e4-countdown-qwen15": {
        "exclude": ["1660s"],  # GTX 1660S is sm75: the strict decoder needs sm80 (GPU_UNSUPPORTED_BY_DECODER)
        "title": "Countdown × Qwen2.5-1.5B-Instruct",
        "task": "countdown",
        "about": "Countdown (dùng các số cho trước và + − × ÷ để ra số đích) với mô hình 1,5B, cùng dữ liệu và cách chia "
        "với E5 (0,5B), để so sánh hai cỡ mô hình. Bài này khó thật: mô hình gốc chỉ đúng 1,6% kể cả khi được 1024 token, "
        "nên mức tăng ở đây không phải do viết gọn. Đoạn 1 (đêm 24/11, 2×5070 Ti) bị lab hủy ở thế hệ 123 do một lỗi lab "
        "(đã sửa); đoạn 2 chạy tiếp từ điểm khôi phục đã kiểm chứng ở thế hệ 110, trên 4 GPU.",
        "repo": "Qwen/Qwen2.5-1.5B-Instruct",
        "revision": "989aa7980e4cf806f80c7fef2b1adb7bc71aa306",
        "tokens": 384,
        "reward": "countdown",
        "first": {"alpha": 5e-4, "sigma": 1e-3, "generations": 150, "reason": PAPER},
        "validation": 25,
    },
    "e5-countdown-qwen05": {
        "title": "Countdown × Qwen2.5-0.5B-Instruct",
        "task": "countdown",
        "about": "Countdown với mô hình 0,5B. Đêm 24/11 bài này đã chạy **ngoài lab** (coordinator và worker dựng tay qua "
        "SSH, khoảng 560 thế hệ qua nhiều đoạn): test 0 → 33/250, và mô hình gốc vẫn đúng 0/250 kể cả khi được 1024 token. "
        "Ở đây chạy lại đúng theo luồng người dùng: notebook → lab → GPU, cùng dữ liệu, cùng 384 token, một đoạn tối đa 200 "
        "thế hệ (dừng sớm khi validation thôi tăng), để xem lab có tái lập được kết quả đó không; điểm khôi phục ghi 10 thế hệ một lần.",
        "repo": "Qwen/Qwen2.5-0.5B-Instruct",
        "revision": "7ae557604adf67be50417f59c2c2f167def9a775",
        "tokens": 384,
        "reward": "countdown",
        "first": {"alpha": 5e-4, "sigma": 1e-3, "generations": 200, "reason": PAPER},
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

SCORER_TEXT = {
    "boxed": "`boxed-number`: lấy số trong `\\boxed{...}` cuối cùng của câu trả lời. Đúng đáp án được 1 điểm; có ô nhưng "
    "sai số được 0,1 điểm (thưởng định dạng); không có ô được 0.",
    "countdown": "`countdown` (reward của TinyZero và bài báo *Evolution Strategies at Scale*): lấy biểu thức trong thẻ "
    "`<answer>` cuối cùng; dùng đúng mỗi số một lần và ra đúng số đích được 1 điểm; có thẻ nhưng sai được 0,1; không có "
    "thẻ được 0. Biểu thức được phân tích cú pháp, không bao giờ được chạy như mã Python.",
    "shaped": "Hàm reward Python tự viết (xem ô dưới).",
}

REWARD = {
    "boxed": r'''from heteroes.v3.scoring import score

SCORER = {"name": "boxed-number", "config": {"answerField": "answer", "formatReward": 0.1}}
TEST_SCORER = SCORER  # "đúng" = score 1: the boxed number equals the answer
make_reward = dict(scorer=SCORER)

# the scorer on a few made-up answers to the first test question (the lab runs exactly this code on every GPU)
demo = splits["test"][0]
texts = [f"... so the answer is \\boxed{{{demo['answer']}}}", "... \\boxed{7}", f"the answer is {demo['answer']}"]
full = {"kind": "declarative", "version": 1, "codeSha256": None, **SCORER}
for text, points in zip(texts, score(full, texts, [demo] * len(texts))[1]):
    print(f"{points:4}  ←  {text!r}")''',
    "countdown": r'''from heteroes.v3.scoring import score

SCORER = {"name": "countdown", "config": {"numbersField": "nums", "targetField": "target"}}
TEST_SCORER = SCORER  # "đúng" = score 1: a valid expression over the given numbers that equals the target
make_reward = dict(scorer=SCORER)

# the scorer on a few made-up answers to the first test question (the lab runs exactly this code on every GPU)
demo = splits["test"][0]
right = tasks.countdown_solution(demo["nums"], demo["target"])
texts = [f"<think>...</think> <answer>{right}</answer>", "<answer>1 + 2</answer>", "không có thẻ answer"]
full = {"kind": "declarative", "version": 1, "codeSha256": None, **SCORER}
for text, points in zip(texts, score(full, texts, [demo] * len(texts))[1]):
    print(f"{points:4}  ←  {text!r}")''',
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

Notebook chạy theo đúng luồng của người nghiên cứu trên lab HeteroES (đăng nhập lab và thêm các máy GPU: xem
`00-chuan-bi.ipynb`):

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
        md(f"""## 4. Bộ chấm (scorer) và reward

{SCORER_TEXT[e["reward"]]}

Reward của một candidate là trung bình điểm trên lô 32 câu train. Trên tập test, **"đúng" nghĩa là điểm 1**. Bộ chấm
là loại *khai báo* (declarative) có sẵn trong lab: lab ghim tên, phiên bản và cấu hình của nó vào công thức run, nên mọi
GPU chấm bằng cùng một đoạn mã."""),
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
({'500 câu' if e['task'] == 'gsm8k' else 'tập validation'}) được chấm mỗi {e['validation']} thế hệ trên coordinator. **Dừng sớm**: nếu validation không vượt mức tốt nhất trước đó
trong 2 lần chấm liên tiếp, notebook hủy run và giữ điểm khôi phục đã kiểm chứng mới nhất (lý do ghi vào
`state/{name}.json`)."""),
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
        backup_interval=10,  # a recovery point every 10 generations (each is a full copy of the weights)
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
        md("""### 6.1 Tốc độ: 1 GPU so với nhiều GPU

Cùng cấu hình chạy thêm 6 thế hệ **chỉ trên một 5070 Ti** để có mốc so sánh. Thời gian một thế hệ đọc từ ledger của
coordinator (ghi mọi candidate: máy nào chấm, lúc nào xong). Thế hệ đầu (nạp mô hình) không tính, và dùng trung vị vì
các thế hệ có chấm validation lâu hơn. Audit = một máy khác chấm lại một candidate; phải ra cùng SHA-256 của câu trả lời."""),
        code('''import statistics

alone = runner.one_gpu_run(lab, experiment, make_trainer, runs[-1][2], segments[-1], COORDINATOR) if not CHAY_MOI else None
names = {d.worker_id: d.name for d in lab.devices()}
speed = {}
for label, run in [(f"đoạn {i}", r) for i, (_, r, _) in enumerate(runs, 1)] + ([("1 GPU", alone)] if alone else []):
    measured = runner.speed(run.id, names)
    if measured is None:
        print(label, ": ledger của coordinator không có trên máy này")
        continue
    print(f"{label}: audit khớp {measured['matched']}/{measured['audits']}, candidate mỗi máy {measured['perDevice']}")
    for machines, seconds in sorted(measured["groups"].items(), key=lambda kv: -len(kv[1])):
        print(f"   {machines:48} {len(seconds):4} thế hệ, trung vị {statistics.median(seconds):6.1f} s/thế hệ")
        speed.setdefault(machines, []).extend(seconds)
speed = {m: {"generations": len(v), "medianSeconds": round(statistics.median(v), 1)} for m, v in speed.items()}
one = next((v["medianSeconds"] for m, v in speed.items() if m == COORDINATOR), None)
most = max(speed, key=lambda m: (m.count("+"), speed[m]["generations"])) if speed else None
if one and most and most != COORDINATOR:
    print(f"→ {most}: nhanh gấp {one / speed[most]['medianSeconds']:.2f} lần một 5070 Ti")'''),
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
finish = {{}}
for label, report in (("mô hình gốc", base), ("cuối đoạn 1", first), (f"chọn (đoạn {{best}})", chosen)):
    ok, n = runner.correct(report)
    f = finish[label] = runner.finished(report, {e['task']!r})
    print(f"{{label:16}} đúng {{ok}}/{{n}} = {{ok / n:6.1%}}   reward {{report['checkpoints'][0]['meanReward']:.4f}}   "
          f"trả lời xong {{f['finished']}}/{{n}}, đúng trên số đã xong {{f['rightAmongFinished'] / max(f['finished'], 1):6.1%}}")'''),
        md("""Cột cuối là phép kiểm tra của lần 1: nếu tỉ lệ đúng chỉ tăng vì mô hình **trả lời xong** nhiều câu hơn (còn tỉ
lệ đúng trên các câu đã xong thì không đổi), thì ES chỉ dạy mô hình viết gọn, không phải suy luận tốt hơn."""),
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
    "selectedSegment": best, "comparison": result, "finished": finish, "speed": speed,
    "oneGpuRun": alone.id if alone else None,
}
out = runner.HERE / "results" / f"{experiment.name}.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\\n")
print("đã lưu", out)'''),
    ]
    return cells


PREPARE = [
    md("""# 00 · Chuẩn bị: lab HeteroES và các máy GPU

Notebook này đi qua những gì cần có **trước** khi chạy một thí nghiệm, theo đúng thứ tự một nhóm nghiên cứu làm:

| Vai trò | Làm gì | Ở đâu |
|---|---|---|
| Người nghiên cứu | đăng nhập lab, xem các GPU đang có | notebook này (mục 1–2) |
| Chủ máy GPU (người cho mượn) | cài worker bằng một dòng lệnh, nhập mã ghép | terminal trên máy GPU (mục 3) |
| Quản trị lab | duyệt máy mới, bật/tắt đóng góp | trang Workers của lab, hoặc notebook này (mục 4) |
| Người nghiên cứu | chọn mô hình, dữ liệu, bộ chấm, cấu hình rồi chạy | các notebook E1–E5 |

Các thí nghiệm của đề tài dùng 4 GPU của 4 máy khác nhau, nối qua Tailscale: hai RTX 5070 Ti (máy của Nhân, kiêm
coordinator, và máy của Nhựt) và hai RTX 3060 (máy của Quang và của Thảo, chạy trong WSL2 trên Windows)."""),
    md("""## 1. Đăng nhập lab

Lab công khai ở `https://lab.heteroes.site`. Đăng nhập một lần trong terminal (mật khẩu không bao giờ được ghi vào
repo hay notebook; phiên có hạn 12 giờ và được lưu ở `~/.config/heteroes-demo/session.json`, quyền 0600):

```bash
python3 scripts/lab-login.py            # hỏi tên và mật khẩu; chạy lại khi phiên hết hạn
```

Một notebook đang chạy dài sẽ tự đọc lại phiên mới khi phiên cũ hết hạn."""),
    code(r"""import sys
from pathlib import Path

HERE = Path.cwd()
SRC = (HERE / ".." / ".." / "src").resolve()
for path in (str(SRC), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

from heteroes.sdk_lab import Lab  # noqa: E402

lab = Lab.from_session()
print(lab)"""),
    md("""## 2. Các GPU của lab

Mỗi máy GPU là một *worker*. `online` = máy đang kết nối với lab; `ON` = chủ máy cho phép lab dùng GPU; `bận` = đang
làm một run hay một lần kiểm thử."""),
    code(r"""for d in lab.devices():
    print(f"{d.name:14} {d.gpu:28} {d.vram_gb:5.1f} GB  online={d.online!s:5} ON={d.on!s:5} bận={d.busy!s:5}"
          f"  coordinator={d.coordinator}")"""),
    md("""## 3. Thêm một máy GPU (chủ máy làm)

Trên máy GPU (Linux, hoặc Ubuntu trong WSL2 trên Windows), dán một dòng lệnh. Lệnh này không cần quyền quản trị, tải bộ
cài từ lab và kiểm SHA-256 từng tệp:

```bash
curl -fsSL 'https://lab.heteroes.site/downloads/install-worker.sh' | HETEROES_DOWNLOADS='https://lab.heteroes.site/downloads' bash
```

Bộ cài kiểm tra driver và GPU, rồi hỏi **mã ghép** (pairing code). Mã ghép tạo ở trang Workers → *Add a GPU computer*,
hoặc bằng ô dưới (đặt `TAO_MA_GHEP = True`). Mã dùng một lần và hết hạn sau vài phút.

Sau khi ghép, chủ máy điều khiển máy của mình bằng `heteroes-worker`:

| Lệnh | Làm gì |
|---|---|
| `heteroes-worker status` | máy đang làm gì, lab nào, GPU, phiên bản runtime |
| `heteroes-worker on` / `off` | cho / thôi cho lab dùng GPU (run đang chạy tiếp trên các máy khác) |
| `heteroes-worker watch` | màn hình trực tiếp: run, thế hệ, GPU, log |
| `heteroes-worker doctor` | kiểm tra driver, ổ đĩa, dịch vụ, mạng, lab và đồng hồ |
| `heteroes-worker clean` | xoá bản tải và runtime cũ (không bao giờ xoá dữ liệu run) |"""),
    code(r"""TAO_MA_GHEP = False  # True: tạo một mã ghép mới cho một máy GPU

if TAO_MA_GHEP:
    reply = lab.request("POST", "/api/v1/devices/pairing-codes", {})
    print("mã ghép:", reply["code"], f"(hết hạn sau {reply.get('expiresInSeconds', '?')} giây)")"""),
    md("""## 4. Duyệt máy mới và bật đóng góp (quản trị lab)

Một máy vừa ghép ở trạng thái `PENDING`: lab chưa giao việc cho nó cho đến khi quản trị viên duyệt. Ô dưới liệt kê máy
chờ duyệt; đặt `DUYET = True` để duyệt tất cả."""),
    code(r"""DUYET = False

for d in lab.request("GET", "/api/v1/platform/devices"):
    print(f"{d['displayName']:14} {d['approvalStatus']:9} ON={d['contributionEnabled']}")
    if DUYET and d["approvalStatus"] == "PENDING":
        lab.request("PATCH", f"/api/v1/platform/devices/{d['deviceId']}", {"approved": True, "workspaceId": lab.workspace})
        print("   → đã duyệt")"""),
    md("""## 5. Lab kiểm thử từng GPU với từng mô hình

Trước run đầu tiên của một mô hình trên một GPU, lab tự **kiểm thử** (qualify) cặp đó: GPU tải mô hình (từ Hugging
Face, hoặc từ lab với mô hình đã train), chạy một phép ES rất nhỏ bằng bộ suy luận nghiêm ngặt và so SHA-256 kết quả
với máy tham chiếu. Lần kiểm thử cũng đo bộ nhớ của từng cỡ lô, để lab gợi ý cỡ lô cho mỗi GPU. GPU không đạt thì không
được dùng cho mô hình đó. Các notebook E1–E5 gọi bước này tự động khi gửi run.

Lỗi hay gặp:

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `GPU_UNSUPPORTED_BY_DECODER` | GPU cũ hơn RTX 30 (ví dụ GTX 1660, sm75): bộ suy luận nghiêm ngặt dùng lệnh nhân ma trận số nguyên của sm80 | dùng GPU từ RTX 30 trở lên |
| Máy WSL nhận việc nhưng không gửi được kết quả | MTU mạng của WSL nhỏ (1280) nên gói Tailscale lớn bị rớt | trong WSL: `sudo ip link set tailscale0 mtu 1200` |
| Ổ C: của Windows đầy | ổ ảo `ext4.vhdx` của WSL nằm trên C: và không tự co lại | `heteroes-worker clean`; nén vhdx bằng `wsl --shutdown` rồi `diskpart` |
| `401` sau 12 giờ | phiên lab hết hạn | chạy lại `scripts/lab-login.py` |"""),
    code(r"""import json

for m in lab.request("GET", "/api/v1/models"):
    print(f"{m['name'][:60]:60} {m.get('status')}")"""),
    md("""Tiếp theo: mở một notebook thí nghiệm (E1–E5). Mỗi notebook đi qua dữ liệu → mô hình → bộ chấm → cấu hình → chạy
trên lab → tốc độ → quá trình học → chấm test → ví dụ trước/sau."""),
]


SUMMARY = [
    md("""# Tổng hợp các thí nghiệm HeteroES

Bảng gom kết quả các notebook thí nghiệm (`results/*.json`). "Đúng" = điểm 1 trên tập test, chấm **một lần** ở cuối;
p là kiểm định McNemar chính xác (mô hình gốc so với checkpoint được chọn). Cột "đúng / đã xong" là tỉ lệ đúng trên các
câu mô hình trả lời xong trong giới hạn token: nếu cột này không tăng thì mức tăng chỉ là do viết gọn hơn."""),
    code(r"""import json
from pathlib import Path

HERE = Path.cwd()


def table(folder):
    print(f"{'thí nghiệm':22} {'mô hình':30} {'n':>5} {'gốc':>5} {'sau ES':>7} {'p':>9}  {'đúng/đã xong: gốc → sau':>24}")
    for path in sorted((folder / "results").glob("*.json")):
        s = json.loads(path.read_text())
        t = s["test"]
        f = s.get("finished") or {}
        cells = [v for k, v in f.items()]
        ratio = (lambda x: x["rightAmongFinished"] / max(x["finished"], 1))
        change = f"{ratio(cells[0]):6.1%} → {ratio(cells[-1]):6.1%}" if cells else "—"
        print(f"{s['name']:22} {s['model'][:30]:30} {t['base']['count']:5} {t['base']['correct']:5} "
              f"{t['selected']['correct']:7} {s['comparison']['mcnemarExactP']:9.2g}  {change:>24}")


table(HERE)"""),
    md("""## Tốc độ: một thế hệ dùng thời gian vào đâu

Trung vị giây mỗi thế hệ theo từng bước, không tính các thế hệ có chấm validation và thế hệ bị tạm dừng. Mốc 1 GPU là run
ngắn 6 thế hệ chỉ trên 5070 Ti của Nhân, cùng cấu hình. Đọc từ nhật ký sự kiện và ledger của coordinator (chỉ có trên máy coordinator). Chỉ bước **chấm candidate** chia được
cho nhiều GPU; cập nhật ES, phát hành trọng số và ghi điểm khôi phục chạy tuần tự trên coordinator, nên thêm GPU không
làm chúng ngắn đi (định luật Amdahl). Các run dưới đây ghi điểm khôi phục **mỗi thế hệ**; từ 25/11 mặc định là 10 thế hệ
một lần."""),
    code(r"""import sys

sys.path[:0] = [str(HERE), str(HERE.parents[1] / "src")]
import matplotlib.pyplot as plt
import runner

names = {d.worker_id: d.name for d in __import__("heteroes.sdk_lab", fromlist=["Lab"]).Lab.from_session().devices()}
rows = []
for path in sorted((HERE / "state").glob("*.json")):
    state = json.loads(path.read_text())
    runs = [(k, v) for k, v in state.get("segments", {}).items()] + ([("one-gpu", state["one-gpu"])] if "one-gpu" in state else [])
    for key, entry in runs:
        p = runner.phases(entry["experimentId"])
        if p and p["generations"]:
            rows.append((f"{path.stem} {key}", entry["workers"], p, runner.device_timing(entry["experimentId"], names)))
steps = ["chấm candidate", "cập nhật ES", "phát hành trọng số", "điểm khôi phục + mở thế hệ sau"]
for label, workers, p, devices in rows:
    print(f"{label:32} {len(devices)} GPU  tổng {p['tổng']:6.1f} s = " + " + ".join(f"{s} {p[s]}" for s in steps))
    for device, d in sorted(devices.items()):
        print(f"      {device:12} vào việc sau {d['startSeconds']:5.1f} s  {d['secondsPerCandidate']:5.2f} s/candidate  "
              f"{d['candidatesPerGeneration']:5.1f} candidate/thế hệ")
fig, ax = plt.subplots(figsize=(9, 0.6 * len(rows) + 1))
left = [0] * len(rows)
for step, color in zip(steps, ["#257de0", "#f47230", "#00b894", "#f2a600"]):
    values = [p[step] for _, _, p, _ in rows]
    ax.barh(range(len(rows)), values, left=left, color=color, label=step, edgecolor="white")
    left = [a + b for a, b in zip(left, values)]
ax.set_yticks(range(len(rows)), [f"{label} ({len(d)} GPU)" for label, _, _, d in rows])
ax.set_xlabel("giây / thế hệ (trung vị)")
ax.legend(loc="lower right", fontsize=8)
plt.tight_layout()
plt.show()"""),
    md("""## Lần 1 (đêm 24 → 25/11) và các run trước đó

Lần 1 nằm trong `v1/` (notebook, kết quả, quyết định). Phát hiện chính, và là lý do làm lại:

| Kết quả lần 1 | Có ý nghĩa? | Vì sao |
|---|---|---|
| E1 GSM8K × Qwen 0.5B, 462 → 528/1319 | không | 320 token: tỉ lệ đúng trên câu đã xong **giảm** 51% → 47%; mức tăng chỉ do trả lời xong nhiều câu hơn |
| E3 GSM8K × Qwen 1.5B, 703 → 871/1319 | không | 320 token: đúng/đã xong 77,5% → 76,8%; 170 trong 251 câu được sửa là câu mà mô hình gốc bị cắt |
| E2 phép nhân × SmolLM2-360M, 0 → 0 | không | mô hình không học được gì |
| E4 Countdown × Qwen 1.5B, 4 → 31/250 | **có** | đúng/đã xong 2,1% → 12,4%; mô hình gốc chỉ 1,6% kể cả với 1024 token |
| Countdown × Qwen 0.5B (24/11, ngoài lab), 0 → 33/250 | **có** | mô hình gốc 0/250 kể cả với 1024 token |
| Phép nhân × Qwen 0.5B (trước 24/11, ngoài lab), 95 → 186/300 | một phần | phần lớn là học ghi `\\boxed{}` (179 → 300 câu có ô), nhưng đúng trên câu có ô vẫn tăng 53% → 62% |

Lần 2 không còn E2. SmolLM2-1.7B (họ Llama) không chạy được trên RTX 3060 12 GB với bộ suy luận nghiêm ngặt: mô hình
này không dùng GQA (32 đầu KV, bằng số đầu attention), nên bộ nhớ KV của lô 8 câu đã cần khoảng 6,1 GB, vượt ngân sách
4,8 GB (40% VRAM) của decoder. Llama 3.2 dùng kiểu RoPE `llama3`: từ 25/11 decoder đã tính được kiểu RoPE này (kiểm
trên CPU so với `transformers`), còn chờ nghiệm thu trên GPU trước khi chạy E2 với Llama-3.2-1B.
SmolLM2-360M thì chạy được nhưng chỉ đúng 2/128 câu GSM8K. Đây là giới hạn hiện tại của hệ thống: mô hình cần GQA
và RoPE mặc định để vừa một GPU 12 GB.

Lần 1 cũng gần như không phân tán: E1 và E2 chạy hoàn toàn trên một 5070 Ti, E3 chỉ có máy Quang góp 14 trong 3200
candidate; chỉ E4 chạy trên 2 GPU (190/190 audit khớp)."""),
    code(r"""table(HERE / "v1")"""),
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
    if not wanted or "00-chuan-bi" in wanted:
        nb = nbf.v4.new_notebook(cells=PREPARE)
        nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
        (HERE / "00-chuan-bi.ipynb").write_text(nbf.writes(nb), encoding="utf-8")
    if not wanted or "tong-hop" in wanted:
        nb = nbf.v4.new_notebook(cells=SUMMARY)
        nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
        (HERE / "tong-hop.ipynb").write_text(nbf.writes(nb), encoding="utf-8")
    print("wrote", sys.argv[1:] or "all notebooks")
