# Kế hoạch review toàn hệ thống HeteroES (2026-10-29)

Hai người review chia nhau: **Người A** lấy "lõi đúng-sai" (số học, engine, sổ cái, giao thức), **Người B** lấy "sản phẩm"
(Recipe v3, agent/runner, backend, giao diện, đóng gói). Hai bên gặp nhau ở các **mối nối** (mục 4) và review chéo ở Pha 3.

Mốc review: `main` = `58cf278c`. Nghiệm thu `PASS` ứng với `10457f9a` (cây nguồn `src-18d0b138`); các commit sau chỉ đổi
`docs/` và `deploy/`. Ba điểm chưa xong (không phải lỗi mới): biên bản nghiệm thu chưa chạy lại cho hash hiện tại; chữ gate
`M5.release` trong `acceptance/registry.py` còn ghi "chưa có release"; `M3.bookkeeping` chưa đo trên runner sản phẩm.

## 1. Nguyên tắc chung

- Đọc theo thứ tự: hợp đồng/ADR → code → test của chính code đó. Mỗi khẳng định trong hợp đồng, tự hỏi "test nào ép
  nó đúng?". Nếu không có test, ghi thành phát hiện loại **T (thiếu test)**.
- Phần đóng băng (`noise/`, `es/`, `ledger/`, `generation_record.py`) và mã kernel strict: **chỉ đọc, không sửa**.
  Nghi ngờ thì ghi phát hiện, chủ dự án quyết.
- Không chạy GPU hay đo throughput khi chưa hỏi chủ dự án (xem REVIEW-GUIDE mục 4 và AGENTS.md). Không SSH sang máy khác,
  không đụng lab đang chạy (chỉ `local-lab.py status`). Baseline CPU, luôn đặt `CUDA_VISIBLE_DEVICES=''`:
  `python3 scripts/accept.py run cpu` (~10 phút) hoặc `scripts/check-all.sh .scratch/checks-<ngày>-<tên>`; riêng backend:
  `.venv-backend/bin/python -m pytest backend/tests -q`.
- Mỗi phát hiện ghi vào `docs/review/FINDINGS-A.md` hoặc `FINDINGS-B.md` theo mẫu: `ID | file:dòng | loại | mức | mô tả | cách tái hiện / bằng chứng | đề xuất`.
  - Loại: **C** đúng-sai (bug), **S** an toàn/bảo mật, **R** độ bền (mất dữ liệu, treo, khôi phục), **T** thiếu test, **D** doc sai/lệch code, **Q** khó bảo trì.
  - Mức: **P0** sai kết quả hoặc mất dữ liệu; **P1** sai trong tình huống hiếm, hoặc lỗ hổng; **P2** nên sửa; **P3** vặt.
- Không sửa code trong lúc review. Gom phát hiện, họp phân loại, rồi mới sửa trên nhánh riêng.

## 2. Phân công

### Người A — Lõi đúng-sai (~23k dòng, dày đặc)

| # | Khu vực | Dòng | Trọng tâm câu hỏi |
| --- | --- | ---: | --- |
| A1 | `runtime/docs/numerical-contract.md`, ADR-001/002/008/012/013/014 | – | Hợp đồng có tự mâu thuẫn không? Mỗi mệnh đề ánh xạ tới code nào? |
| A2 | `noise/` (không tính `_thresholds_v2.py` 2 255 dòng là bảng sinh tự động), `es/` | ~1 500 | Danh tính nhiễu có lọt worker/attempt/lease không? FP32 theo thứ tự candidate chuẩn? Snapshot/khôi phục có chính xác từng bit? Bảng v2 có kiểm lại bằng `scripts/gen-noise-v2-table.py` + `check-noise-v2.py` |
| A3 | `ledger/ledger.py` (1 308), `generation_record.py` | ~1 700 | Máy trạng thái candidate/attempt/lease: chuyển trạng thái không hợp lệ, lease hết hạn song song, ghi đôi, giao dịch SQLite (crash giữa chừng), "lỗi hạ tầng không bao giờ thành reward 0" |
| A4 | `coordinator.py`, `worker.py`, `worker_api.py`, `http_transport.py`, `dispatch`, `manifest` | ~3 500 | Xác thực/ủy quyền worker, replay, kích thước payload, timeout, cách ly worker lệch, tính idempotent của retry |
| A5 | `strict/` — thứ tự: `strict_backend.py` → `integer_projection`/plan B22 → `strict_decoder*.py` → `frozen_int8*.py`/LoRA → kernel NVRTC (`integer_cuda.py`, `strict_cuda.py`) | 8 835 | Cùng token trên mọi GPU: có chỗ nào phụ thuộc thứ tự cộng dấu phẩy động / atomic / số SM? Biên chỉ số, tràn int, bộ nhớ chưa khởi tạo, đồng bộ stream/graph; `sourceSha256` có phủ đủ file ảnh hưởng không |
| A6 | `eval/` (1 010) | ~1 000 | Chấm điểm candidate, compact decode, workload: có chỗ nào kết quả phụ thuộc thiết bị? |
| A7 | `acceptance/` (registry, probes, mutants, golden) | ~3 000 | Gate có thật sự chứng minh điều nó nói? Mutant có bắt được lỗi không (mutation kill rate)? Có check nào luôn xanh vì không kiểm gì? |

### Người B — Sản phẩm (~48k dòng, nhẹ hơn mỗi dòng)

| # | Khu vực | Dòng | Trọng tâm câu hỏi |
| --- | --- | ---: | --- |
| B1 | `v3/` (Recipe v3: CLI, run cục bộ/phân tán, `audit.py`, tracker, data) | 4 719 | Run tái lập được? Kiểm toán phát hiện đúng sai lệch? Đường nhập dữ liệu/đường dẫn có bị path traversal? |
| B2 | `product/` (agent, `agent_protocol`, `worker_cli`, `run_supervisor`, `runner`, recovery, telemetry, qualification v1/v2) | 7 395 | Thiết bị mất kết nối giữa run; phục hồi (resume) đúng điểm; tiến trình con mồ côi; tải file (`downloads.py`) có kiểm hash/chữ ký; bookkeeping tăng theo thế hệ (M3.bookkeeping) |
| B3 | `model/`, `study/`, `demo/`, `sdk.py`, `sdk_lab.py` | ~3 500 | API công khai của nhà nghiên cứu: lỗi có rõ ràng; pickle/eval/exec bất cẩn khi nạp model/schema |
| B4 | `backend/` (FastAPI: tài khoản, thiết bị, `agent_scheduling`, `recovery_storage`, policy, `store`) | 7 741 | Phân quyền từng route (ai xem/ sửa run, thiết bị của ai), phiên/token, giới hạn tốc độ, lập lịch lease với sổ cái (mối nối M1), lưu trữ phục hồi: dung lượng, xóa, toàn vẹn |
| B5 | `frontend/src/` (159 file) + `packages/product-ui` | ~16 000 | Chỉ review sâu: luồng đăng nhập, đăng ký thiết bị, tạo/dừng run, hiển thị kiểm toán (không nói sai kết quả). Phần còn lại đọc lướt và dựa vào `scripts/check-web-*.mjs` + i18n |
| B6 | `desktop/` (Electron worker/server), `deploy/`, `scripts/` vận hành (`local-lab.py`, `install-worker.sh.in`, `publish-local-installers.py`, `build-*`) | ~7 500 | Electron: `nodeIntegration`/`contextIsolation`, IPC, tự cập nhật, chữ ký gói; script cài chạy `sudo`/`curl|sh` thế nào; systemd unit sau sửa venv |

Nếu một người nhanh hơn, B5 là phần dễ chuyển sang A (hoặc ngược lại A7 chuyển sang B).

## 3. Lịch chạy (4 pha)

**Pha 0 — Chuẩn bị (cả hai, ~nửa ngày).** Đọc README, AGENTS.md, HANDOFF, REVIEW-GUIDE. Chạy `accept.py run cpu` và
`check-archive-fixtures.py`, `build-evidence-index.py --check` để chắc cây sạch. Cùng nhau vẽ sơ đồ luồng một candidate từ
"lab tạo run" → backend → coordinator → ledger → worker → strict engine → kết quả → cập nhật ES → bản ghi thế hệ. Sơ đồ
này là bản đồ chung cho cả hai.

**Pha 1 — Đọc có chủ đích (song song, phần lớn thời gian).** Mỗi người làm khu vực của mình theo thứ tự bảng ở mục 2.
Với mỗi khu vực: (1) đọc hợp đồng/ADR, (2) liệt kê 5–10 bất biến, (3) đọc code tìm chỗ vi phạm, (4) đọc test xem bất biến có
được ép không, (5) viết phát hiện.

**Pha 2 — Mối nối (hai người cùng ngồi, mục 4).** Từng mối nối review chung vì mỗi nửa hiểu một đầu.

**Pha 3 — Review chéo + phân loại.** Đổi chỗ: A đọc lại B2 và B4 (phần giao thức/ủy quyền), B đọc lại A3 và A4 (đọc như
người dùng API). Người "ngoài" hay thấy chỗ giả định ngầm. Sau đó họp phân loại: P0/P1 thành việc sửa có chủ, P2/P3 vào backlog,
D (doc sai) sửa luôn; T (thiếu test) quyết định cái nào cần trước M3/M5.

## 4. Mối nối cần review chung

1. **Sổ cái ↔ backend lập lịch**: `ledger` (lease, attempt) so với `backend/agent_scheduling.py` và `runtime/.../product/agent.py`. Ai là nguồn sự thật khi lease hết hạn mà worker vẫn gửi kết quả?
2. **Giao thức coordinator ↔ agent**: `worker_api.py`, `http_transport.py` với `agent_protocol.py`. Phiên bản giao thức, trường thiếu, xác thực hai chiều.
3. **Khôi phục (recovery)**: `es/` snapshot → `recovery_storage.py` (backend) → `run_supervisor.py`. Khôi phục "chính xác" có còn đúng sau khi đi qua lưu trữ?
4. **Danh tính engine ↔ đóng gói**: `sourceSha256`/`integerSourceSha256` với `check-source-packages.py`, `build-worker-profile.py`. Gói worker cài trên máy khách có đúng byte nguồn đã nghiệm thu không?
5. **Kiểm toán**: `v3/audit.py` ↔ UI hiển thị kết quả: UI có thể "tô xanh" thứ audit chưa kiểm không?
6. **Nghiệm thu ↔ thực tế**: mỗi gate trong `registry.py` đối chiếu với tuyên bố trong HANDOFF/RELEASE-NOTES. Tìm gate "PASS" mà check bên dưới yếu.

## 5. Danh sách "đã biết, đừng báo là lỗi mới"

- 3 điểm chưa xong ở đầu tài liệu; `M1.architectures` và `M3.full-disk` DEFERRED.
- Hai worker strict trong một tiến trình trên một GPU hỏng khi capture CUDA graph (lab không dùng cách này).
- `strict_int8_lora_v1` chỉ dùng standalone/SDK, không có trong lab.
- Qualification v1/v2 và profile `desktop-v1` còn giữ cố ý (lab vẫn resume run cũ).
- `strict/integer_cuda.py`, `strict_cuda.py` chưa tách file cố ý (hash danh tính).
- Mục tiêu 80% vLLM đã đóng "không đạt" (72,8%).
- Vulture báo nhầm route FastAPI và hàm notebook công khai.

## 6. Cách kết thúc

Khi xong: mỗi người nộp `FINDINGS-*.md` + 1 đoạn "mức tin cậy" cho từng khu vực (đã đọc kỹ / lướt / chưa đọc). Chủ dự án
duyệt danh sách P0/P1 rồi mới mở nhánh sửa. Sau khi sửa xong, chạy lại nghiệm thu cho hash mới (mục Next steps 1 trong HANDOFF).
