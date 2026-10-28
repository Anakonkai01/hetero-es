# Hướng dẫn review HeteroES (sau refactor 2026-10-28)

Tài liệu này dành cho người review code lần đầu. Nó nói nên đọc gì trước, mỗi phần code làm gì, những điều không được
phá, cách chạy kiểm tra, và những gì đã bị gỡ khỏi `main` cùng chỗ tìm lại.

**Dự án khẳng định gì.** HeteroES không đưa ra thuật toán ES mới và không nhằm chứng minh ES học được. Đóng góp là hệ thống:
hậu huấn luyện LLM bằng ES trên nhiều GPU gia đình khác loại, chạy đúng, tái lập được và đo được, dưới dạng một lab mà nhà
nghiên cứu đăng ký và tùy chỉnh được.

## 1. Thứ tự đọc

1. `README.md` (bố cục repo), rồi `AGENTS.md` (luật làm việc chung) và `docs/HANDOFF.md` (trạng thái hiện tại).
2. `runtime/docs/numerical-contract.md`: hợp đồng số học (nhiễu, cập nhật, khôi phục chính xác). Đây là phần quan trọng
   nhất; các ADR trong `runtime/docs/adr/` giải thích từng quyết định (ADR-001 nhiễu CPU PCG64, ADR-002 sổ cái
   candidate/attempt/lease, ADR-008 Recipe v3, ADR-012/013/014 engine strict).
3. `runtime/src/heteroes/noise`, `es`, `ledger`, `generation_record.py`: lõi số học và sổ cái (phần đóng băng, xem mục 3).
4. `runtime/src/heteroes/strict/`: engine đánh giá strict (cùng một chuỗi token trên mọi GPU NVIDIA được hỗ trợ).
   Đọc `strict_backend.py` trước (điểm vào), rồi `runtime/docs/strict-reference-v1.md`, `strict-decoder-v1.md`,
   `integer-projection-v1.md`.
5. `runtime/src/heteroes/v3/` (Recipe v3: chạy, phân tán, kiểm toán, theo dõi) và `product/` (agent, worker CLI,
   giám sát run).
6. `backend/` (API của lab), `frontend/src/` (giao diện web), `desktop/` (ứng dụng Electron).
7. `acceptance/registry.py` và `docs/acceptance/STATUS-*.md`: mọi gate M0–M6 và kiểm tra nào chứng minh gate đó.

## 2. Bản đồ module (số dòng không tính test, đếm ngày 2026-10-28)

| Thư mục | File | Dòng | Vai trò |
| --- | ---: | ---: | --- |
| `runtime/src/heteroes/strict/` | 21 | 8 835 | Engine strict: số học tham chiếu, plan số nguyên B22, kernel NVRTC (prefill/decode, TMA, attention), các decoder, int8 đóng băng + LoRA |
| `runtime/src/heteroes/eval/` | 10 | 1 010 | Đánh giá chung: workload, sinh văn bản HF, compact decode, chấm điểm candidate, đo theo pha |
| `runtime/src/heteroes/noise/` | 10 | 3 037 | Engine nhiễu chuẩn (CPU PCG64, v2 số nguyên) và bản CUDA |
| `runtime/src/heteroes/es/` | 6 | 690 | Nhiễu loạn, snapshot/khôi phục, cập nhật ES |
| `runtime/src/heteroes/ledger/` | 2 | 1 367 | Sổ cái SQLite: candidate, attempt, lease |
| `runtime/src/heteroes/v3/` | 22 | 4 719 | Recipe v3: CLI `heteroes`, run cục bộ/phân tán, kiểm toán, tracker, chấm điểm, dữ liệu |
| `runtime/src/heteroes/product/` | 33 | 7 395 | Agent thiết bị, worker CLI Linux, giám sát run, phục hồi, telemetry, qualification |
| `runtime/src/heteroes/model/`, `study/`, `demo/` | 20 | 2 993 | Nạp model/schema tham số, study, dashboard cho notebook nhà nghiên cứu |
| `runtime/src/heteroes/*.py` | 23 | 5 487 | Coordinator, worker, transport HTTP, dispatch, manifest, SDK (`sdk.py`, `sdk_lab.py`) |
| `backend/` | 44 | 7 741 | API FastAPI của lab: tài khoản, thiết bị, lập lịch, lưu trữ phục hồi, chính sách |
| `frontend/src/` | 159 | 14 503 | Web UI (React) |
| `desktop/`, `packages/product-ui/src/` | 30 | 6 811 | Ứng dụng Worker/Server (Electron) và UI dùng chung |
| `acceptance/`, `scripts/` | 58 | 8 306 | `scripts/accept.py`, probe nghiệm thu, đóng gói, vận hành lab |

Hai file lớn nhất là `strict/integer_cuda.py` (1 847 dòng) và `strict/strict_cuda.py` (1 661 dòng); phần lớn là chuỗi
mã nguồn CUDA.

## 3. Bất biến không được phá

- **Recipe v1 đóng băng.** `noise/`, `es/`, `ledger/` và `generation_record.py` chỉ được định dạng lại khi có chứng minh
  AST bằng nhau (`scripts/check-python-ast.py`). Đổi hành vi cần chủ dự án duyệt riêng.
- **Danh tính nhiễu** không chứa thông tin worker/attempt/lease. Nhiễu loạn là nhân và cộng FP32 tách rời, công bố FP16;
  cộng dồn cập nhật là FP32 theo thứ tự candidate chuẩn. Khôi phục phải chính xác; lệch thì cách ly worker. Lỗi hạ tầng
  không bao giờ bị đổi thành reward 0.
- **Engine strict.** Mã nguồn kernel là một phần danh tính (`sourceSha256`, `integerSourceSha256`, ...): sửa một ký tự
  là ra danh tính mới. `strict_b22_v1` hứa cùng token trên mọi GPU được hỗ trợ (SM86, SM120 đã đo).
- **Một bộ trọng số mỗi GPU (D1).** Run strict không cho coordinator dùng chung GPU với một worker.
- **Evidence bất biến.** Evidence nằm trên nhánh `evidence-archive`; thêm thư mục mới, không sửa thư mục cũ.

## 4. Cách kiểm tra

```bash
python3 scripts/accept.py list                         # mọi kiểm tra và gate
python3 scripts/accept.py run cpu                      # ~10 phút, không cần GPU (check-all + selftest)
HETEROES_GPU_ACCEPTANCE=1 python3 scripts/accept.py run gpu perf faults package mutation --keep
python3 scripts/accept.py report --write               # ghi docs/acceptance/STATUS-*.md
python3 scripts/check-archive-fixtures.py              # fixture test giống hệt bản lưu trữ
python3 scripts/build-evidence-index.py --check        # chỉ mục evidence khớp nhánh lưu trữ
```

Chạy GPU cần chủ dự án cho phép. Máy 3060 của Thảo chạy qua `accept.py remote 3060-wsl|3060-native` (cần SSH được cho
phép).

## 5. Refactor 2026-10-28 đã làm gì và tìm lại ở đâu

Trạng thái trước refactor: tag cục bộ `archive/pre-refactor-2026-10` (commit `c33eb61e`; tag không được push). Lịch sử
git của `main` vẫn chứa mọi file đã gỡ (`git show c33eb61e:<đường dẫn>`).

| Commit | Thay đổi | Bằng chứng |
| --- | --- | --- |
| Refactor 1 | `docs/evidence` (223 thư mục, 11 079 file), `runtime/artifacts` (2 694), `docs/archive` (83) sang nhánh `evidence-archive`; `docs/EVIDENCE-INDEX.md` sinh từ nhánh đó | `git ls-tree -r` của nhánh bằng đúng của `c33eb61e` cho các đường dẫn đó; 15 fixture được chép giống hệt (`check-archive-fixtures.py`) |
| Refactor 2 | Handoff cũ, kế hoạch human-review, ghi chú DeepSeek/vLLM, `HETEROES_LLM_MASTER/STATUS.md`, `runtime/docs/report`, `planning` sang nhánh lưu trữ | cùng blob, so `ls-tree` |
| Refactor 3 | Gỡ thử nghiệm không chọn: decoder FP16 của hãng, view trọng số vLLM, probe SGLang/vLLM, công cụ benchmark/cluster/failure-campaign/sweep C1 (`admission`, `benchmark_stats`, `eval.diagnostics`), tầng demo GSM8K, 3 notebook khám phá, kèm test của chúng | đồ thị import AST từ các điểm vào thật: không điểm vào nào tới được các module này |
| Refactor 4 | 20 module engine strict từ `heteroes/eval` sang gói `heteroes/strict` (giữ tên file) | AST mỗi module (bỏ dòng import) và các chuỗi dài (mã CUDA) có hash giống hệt trước/sau |
| Refactor 5, 6 | Tách `worker_cli.py` (1 321 → 944 dòng: `downloads.py`, `worker_lab.py`, `worker_terminal.py`) và `agent.py` (1 086 → 942: `agent_protocol.py`) | mọi định nghĩa cấp cao có AST giống hệt ở file mới |

**Cố ý không làm, và lý do:**

- Không tách `strict/integer_cuda.py` và `strict/strict_cuda.py`: danh tính engine băm toàn bộ byte của từng file này;
  chuyển code Python khởi chạy kernel sang file khác sẽ đưa nó ra khỏi phạm vi hash đó.
- Không gỡ luồng qualification v1/v2 và profile `desktop-v1`: lab đang chạy vẫn nhận thiết bị và resume run đã lưu theo
  các phiên bản đó; gỡ là đổi hành vi sản phẩm.
- Không gom `runtime/scripts` vào `scripts/`: test, probe nghiệm thu và gói worker (`run_worker.py`) gọi chúng theo đường dẫn
  hiện tại.
- Giữ `heteroes.demo` (dashboard, `DemoLab`): `sdk_lab.py` và notebook nhà nghiên cứu dùng. Vulture chỉ báo vài hàm
  notebook công khai và route FastAPI (báo nhầm), nên không gỡ thêm code chết.
