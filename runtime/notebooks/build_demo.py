"""Write demo.ipynb (cells only, no outputs): an ES experiment from start to finish with the SDK, in Vietnamese.

Run: python runtime/notebooks/build_demo.py   (any Python with nbformat)
"""

from pathlib import Path

import nbformat as nbf

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
    md("""# Demo HeteroES: hậu huấn luyện một mô hình ngôn ngữ bằng ES, từ đầu đến cuối

Notebook này đi qua toàn bộ một thí nghiệm như người nghiên cứu dùng HeteroES qua SDK Python:

| Bước | Người nghiên cứu viết | HeteroES làm |
|---|---|---|
| 1. Chuẩn bị | chọn máy chạy | kiểm tra GPU |
| 2. Dữ liệu | sinh câu hỏi phép nhân | chia train/validation/test cố định theo seed, ghim mã băm |
| 3. Mô hình | tên mô hình trên Hugging Face | ghim phiên bản và SHA-256 từng tệp |
| 4. Reward | chọn bộ chấm (hoặc tự viết hàm Python) | ghim danh tính bộ chấm vào cấu hình |
| 5. Cấu hình | `ESConfig`: α, σ, số candidate, số thế hệ | tạo recipe có mã băm riêng |
| 6. Chạy | `train()` (máy này) hoặc `submit()` (lab) | điều phối, ghi ledger, audit, công bố trọng số |
| 7. Đánh giá | chọn checkpoint | tái dựng checkpoint từ ledger, chấm tập test, kiểm định thống kê |
| 8. Nối tiếp | tham số mới | tạo mô hình mới từ trọng số đã kiểm chứng, kèm nguồn gốc |

Bài toán: phép nhân (ba chữ số × một chữ số, hai chữ số × hai chữ số), mô hình phải trả lời **chỉ một con số trong
`\\boxed{}`** với tối đa 24 token. Mô hình Qwen2.5-0.5B-Instruct ban đầu thường trả lời dài dòng hoặc sai định dạng.

Chạy bằng kernel có PyTorch (ví dụ kernel `ai`). Mặc định notebook chạy trên máy này; mục 9 gửi cùng thí nghiệm lên lab."""),
    md("""## 1. Chuẩn bị

`GENERATIONS` là số thế hệ của lượt chạy đầu. 20 thế hệ mất khoảng 8 phút trên RTX 5070 Ti."""),
    code("""import json
import sys
from pathlib import Path

# The runtime sources sit next to this notebook (runtime/notebooks -> runtime/src); an installed SDK works as well.
SRC = (Path.cwd() / ".." / "src").resolve()
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import torch

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"  # the coordinator goes to the GPU when there is one
WORK = Path.home() / "heteroes-demo"
WORK.mkdir(exist_ok=True)
GENERATIONS = 20
print("Thiết bị:", DEVICE, torch.cuda.get_device_name(0) if DEVICE == "cuda" else "")
print("Thư mục làm việc:", WORK)"""),
    md("""## 2. Dữ liệu

3.000 câu hỏi được sinh tất định từ một seed, nên ai chạy lại cũng được đúng bộ dữ liệu này. HeteroES chia nó
80/10/10 thành train, validation và test; huấn luyện chỉ nhìn thấy train."""),
    code("""import importlib.util
from collections import Counter

spec = importlib.util.spec_from_file_location("arith", SRC.parent / "scripts" / "build_arithmetic_dataset.py")
arith = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arith)

DATA = WORK / "arithmetic.jsonl"
if not DATA.exists():
    arith.write(arith.build_rows(3000, seed=20261124), DATA, 20261124)
rows = [json.loads(line) for line in DATA.read_text().splitlines()]
print(len(rows), "câu hỏi;", dict(Counter(r["kind"] for r in rows)))
for r in rows[:3]:
    print("-", r["prompt"], "→ đáp án", r["answer"])"""),
    md("""## 3. Mô hình

Mô hình được ghim theo một commit cụ thể trên Hugging Face. Mỗi tệp được ghi lại SHA-256; mọi máy chạy thí nghiệm
đều kiểm tra lại các mã băm này trước khi làm việc, nên tệp đến từ đâu (Hugging Face, bản sao, ổ USB) cũng như nhau."""),
    code("""import shutil
from huggingface_hub import snapshot_download
from heteroes.catalog import PINNED_MODEL_ID, PINNED_REVISION
from heteroes.v3.model import file_manifest

MODEL = WORK / "models" / "qwen2.5-0.5b-instruct"
if not MODEL.exists():
    cache = snapshot_download(PINNED_MODEL_ID, revision=PINNED_REVISION, allow_patterns=["*.json", "*.safetensors", "*.txt"])
    shutil.copytree(cache, MODEL)  # plain files, no symbolic links
for name, sha in file_manifest(MODEL).items():
    print(f"{name:28} {sha[:16]}…")"""),
    md("""### Mô hình gốc trả lời thế nào?

Thử năm câu cuối của bộ dữ liệu, sinh câu trả lời theo cách tương tự thí nghiệm (giải mã tham lam, tối đa 24 token)."""),
    code("""from transformers import AutoModelForCausalLM, AutoTokenizer

tok = AutoTokenizer.from_pretrained(MODEL)
lm = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float16).to(DEVICE).eval()
for r in rows[-5:]:
    text = tok.apply_chat_template([{"role": "user", "content": r["prompt"]}], tokenize=False, add_generation_prompt=True)
    ids = tok(text, return_tensors="pt").to(DEVICE)
    out = lm.generate(**ids, max_new_tokens=24, do_sample=False)
    print(repr(tok.decode(out[0, ids.input_ids.shape[1]:], skip_special_tokens=True)), "| đáp án", r["answer"])
del lm
torch.cuda.empty_cache() if DEVICE == "cuda" else None"""),
    md("""## 4. Reward

Dùng bộ chấm khai báo có sẵn `boxed-number`: 1 điểm khi số trong `\\boxed{}` đúng, 0,1 điểm khi đúng định dạng nhưng
sai số, 0 điểm khi không có `\\boxed{}`. Reward của một candidate là trung bình trên lô câu hỏi.

Có thể thay bằng một hàm Python tự viết (ô dưới có ví dụ). Mã nguồn của hàm được ghim bằng SHA-256: sửa hàm là
một thí nghiệm khác. Hàm lỗi hay trả về giá trị không hữu hạn thì thế hệ dừng lại, không bao giờ bị coi là 0 điểm."""),
    code("""from heteroes.sdk import reward
from heteroes.v3.scoring import score

SCORER = {"name": "boxed-number", "config": {"answerField": "answer", "formatReward": 0.1}}


@reward("boxed-or-nothing@1")  # an equivalent Python reward, shown for reference (not used below)
def boxed_or_nothing(completions, rows):
    import re

    out = []
    for text, row in zip(completions, rows):
        found = re.findall(r"\\\\boxed\\{([^{}]*)\\}", text)
        out.append(0.0 if not found else 1.0 if found[-1].strip() == row["answer"] else 0.1)
    return out


demo = [rows[0], rows[0], rows[0]]
texts = [f"\\\\boxed{{{rows[0]['answer']}}}", "\\\\boxed{1}", "Kết quả là " + rows[0]["answer"]]
full = {"kind": "declarative", "version": 1, "codeSha256": None, **SCORER}
print("boxed-number:", score(full, texts, demo)[1])
print("hàm Python:  ", boxed_or_nothing(texts, demo))"""),
    md("""## 5. Cấu hình thí nghiệm

Mỗi thế hệ: 32 candidate, mỗi candidate là trọng số cộng nhiễu σ·ε, được chấm trên 32 câu hỏi; sau đó trọng số
dịch về phía các candidate tốt với tốc độ học α."""),
    code("""from heteroes.sdk import ESConfig, ESTrainer

args = ESConfig(
    model_path=str(MODEL),
    model_id=PINNED_MODEL_ID,
    train_dataset=str(DATA),
    prompt_field="prompt",
    population=32,
    generations=GENERATIONS,
    sigma=0.001,
    alpha=0.0005,
    batch_size=32,
    max_new_tokens=24,
)
trainer = ESTrainer(args, scorer=SCORER)
config = trainer.config()
print({k: config[k] for k in ("population", "generations", "alpha", "maxNewTokens", "decoder")})"""),
    md("""## 6. Chạy

`train()` chạy coordinator và worker của HeteroES trên máy này, với đúng giao thức, ledger và audit mà lab dùng.
Biểu đồ cập nhật sau mỗi thế hệ."""),
    code("""import time
import matplotlib.pyplot as plt
from IPython.display import clear_output

RUN_A = WORK / f"run-a-{time.strftime('%Y%m%d-%H%M%S')}"
history = []


def show(event):
    if event.get("event") != "generation_done":
        return
    history.append(event["mean_reward"])
    clear_output(wait=True)
    plt.figure(figsize=(7, 3))
    plt.plot(range(1, len(history) + 1), history, color="#2a78d6")
    plt.ylim(0, 1)
    plt.xlabel("thế hệ")
    plt.ylabel("reward trung bình (lô train)")
    plt.show()
    print(f"thế hệ {event['generation']}: reward {event['mean_reward']:.3f}, {event['total_seconds']:.1f} s, "
          f"trọng số mới {event['child_sha256'][:12]}…")


summaries = trainer.train(RUN_A, device=DEVICE, log=show)"""),
    md("""## 7. Đánh giá trên tập test

`evaluate` tái dựng từng checkpoint **chỉ từ các bản ghi cập nhật trong ledger** (kiểm tra mã băm từng thế hệ), rồi
chấm toàn bộ tập test, phần huấn luyện chưa từng thấy. `compare` so hai checkpoint trên cùng các câu: kiểm định
McNemar chính xác và khoảng tin cậy bootstrap 95%."""),
    code("""from heteroes.v3.comparison import compare
from heteroes.v3.evaluation import evaluate


def table(report):
    for c in report["checkpoints"]:
        n = len(c["scores"])
        label = "mô hình gốc" if c["generation"] < 0 else f"sau {c['generation'] + 1} cập nhật"
        print(f"{label:22} đúng {sum(s == 1 for s in c['scores']) / n:6.1%}   "
              f"đúng định dạng {sum(s > 0 for s in c['scores']) / n:6.1%}")


report_a = evaluate(RUN_A, MODEL, [-1, GENERATIONS - 1], "test", device=DEVICE)
table(report_a)
result = compare(report_a, report_a, -1, GENERATIONS - 1)
print(f"sửa đúng {result['fixed']}, làm sai {result['broke']}, McNemar p = {result['mcnemarExactP']:.2g}, "
      f"khoảng tin cậy 95% của mức tăng reward [{result['bootstrapCI'][0]:.3f}; {result['bootstrapCI'][1]:.3f}]")"""),
    md("""## 8. Nối tiếp run với tham số mới

Run A đã xong. `continue_from` tạo một mô hình mới từ trọng số cuối đã kiểm chứng của nó, kèm tệp
`heteroes-lineage.json` ghi nguồn gốc. Tệp này nằm trong danh tính của mô hình mới. Run B chạy trên mô hình đó với
tốc độ học giảm một nửa, và thế hệ 0 của nó phải bắt đầu đúng từ trọng số cuối của run A."""),
    code("""import sqlite3
from heteroes.sdk import continue_from

AFTER_A = WORK / (RUN_A.name + "-model")
continue_from(RUN_A, MODEL, AFTER_A)
lineage = json.loads((AFTER_A / "heteroes-lineage.json").read_text())
print("nguồn:", lineage["source"], "| trọng số", lineage["weightsSha256"][:16], "…")

args_b = ESConfig(**{**args.__dict__, "model_path": str(AFTER_A), "model_id": PINNED_MODEL_ID + "+run-a",
                     "alpha": args.alpha / 2, "generations": 10})
RUN_B = WORK / RUN_A.name.replace("run-a", "run-b")
history.clear()
ESTrainer(args_b, scorer=SCORER).train(RUN_B, device=DEVICE, log=show)

with sqlite3.connect(RUN_B / "ledger.sqlite") as db:
    parent = db.execute("SELECT parent_weights_sha256 FROM generation WHERE generation = 0").fetchone()[0]
print("thế hệ 0 của run B bắt đầu từ", parent[:16], "… =", "ĐÚNG" if parent == lineage["weightsSha256"] else "SAI",
      "trọng số cuối của run A")
table(evaluate(RUN_B, AFTER_A, [-1, 9], "test", device=DEVICE))"""),
    md("""## 9. Gửi cùng thí nghiệm lên lab (tùy chọn)

Trên lab, GPU của các thành viên làm worker, lab xếp hàng, chọn máy, audit chéo và lưu điểm phục hồi. Đặt
`RUN_ON_LAB = True`, nhập địa chỉ lab và tài khoản. Coordinator nên là một máy có GPU."""),
    code("""RUN_ON_LAB = False

if RUN_ON_LAB:
    from heteroes.sdk_lab import Lab

    lab = Lab.connect(input("Lab URL: ").strip() or "https://lab.heteroes.site")
    for device in lab.devices():
        print(device)
    coordinator = input("Coordinator (tên máy có GPU): ").strip()
    workers = [w.strip() for w in input("Worker (cách nhau bằng dấu phẩy): ").split(",") if w.strip()]
    run = trainer.submit(lab, coordinator, workers, name="demo-so-hoc")
    run.watch()"""),
    md("""## Tóm tắt

- Một thí nghiệm ES được mô tả hoàn toàn bằng dữ liệu, mô hình, bộ chấm và `ESConfig`; HeteroES ghim tất cả bằng mã
  băm.
- Mọi checkpoint được tái dựng từ ledger trước khi đánh giá, nên con số trên tập test gắn với đúng chuỗi cập nhật đã ghi.
- Một run đã xong có thể được nối tiếp với tham số mới mà vẫn kiểm chứng được nguồn gốc trọng số.

Kết quả của notebook phụ thuộc phiên bản PyTorch của kernel: cùng cấu hình chạy với hai phiên bản PyTorch khác nhau có
thể cho câu trả lời lệch nhau khi dùng decoder thường. Bộ suy luận nghiêm ngặt (`decoder="strict_b22_v1"`) cho cùng
câu trả lời trên mọi GPU đã nghiệm thu."""),
]

notebook = nbf.v4.new_notebook(cells=cells)
notebook.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
Path(__file__).with_name("demo.ipynb").write_text(nbf.writes(notebook), encoding="utf-8")
print("wrote demo.ipynb with", len(cells), "cells")
