# Kế hoạch cho Codex (chạy tự động): sửa phát hiện review → tách backend thành nhiều service → HeteroES MiniCloud

Lập 2026-10-31 (Claude Opus, sau 4 vòng hỏi chủ dự án). Người làm: **Codex, chạy tự động dài, không có người giám sát**.
Repo 1: `~/projects/heteroes` (GitHub `Anakonkai01/hetero-es`). Repo 2 (mới): `~/projects/heteroes-minicloud`.

## Context

- 2026-10-29 chủ dự án và một người bạn bắt đầu review HeteroES (`docs/REVIEW-PLAN.md`). Phần lõi (người A) có 19 phát hiện
  trong `docs/review/FINDINGS-A.md` (A-001 … A-019, **chưa commit**, nằm trên `main` cùng đợt sắp xếp lại tài liệu).
  Phần ứng dụng (người B) có ghi chú ở `~/projects/app_finding.md`: Lab Server là một khối, `backend/` là các file `.py`
  phẳng và rối, `routes_*.py` trộn API + logic + SQL, chưa có lớp trung gian với DB, `Store` là lớp gom mọi SQL trên SQLite.
  Người bạn còn hỏi 2 câu: Lab Server đóng vai trò mấy loại server, và dữ liệu khác (kết quả thí nghiệm, bản sao lưu) nằm ở đâu.
  Cả hai chưa review hết: trong lúc sửa, gặp lỗi mới thì cứ sửa luôn, không cần hỏi (theo luật ở mục 1).
- Đồ án cuối kỳ môn Cloud (`~/projects/Báo Cáo Cuối Kỳ.docx`, tên file dạng NFD, mở bằng glob `Ba*.docx`):
  - Dựng MyMiniCloud gồm 9 loại server, mỗi server một container, chung network `cloud-net`, chạy bằng `docker-compose`.
  - Mỗi service có Dockerfile, `restart: unless-stopped`, cổng 80xx, volume.
  - Push ít nhất 1 image lên Docker Hub; deploy lên AWS EC2 Ubuntu, truy cập được qua public IP.
  - Chấm điểm: phần demo cơ bản 5 điểm, 10 yêu cầu mở rộng × 0,5 điểm.
  - Báo cáo 5 chương + phụ lục.
- Kết quả cần có: (A) phát hiện được sửa có bằng chứng, nghiệm thu chạy lại; (B) backend chia lớp và tách thành nhiều
  service, chạy được với Postgres/Keycloak/MinIO, bản desktop vẫn dùng SQLite và đăng nhập cũ; (C) repo `heteroes-minicloud`
  chạy HeteroES thành một mini-cloud 9 server (ở nhà và trên EC2), có minh chứng và bản nháp báo cáo.

## Quyết định của chủ dự án (đã chốt 2026-10-31)

| Chủ đề | Quyết định |
| --- | --- |
| Vùng đóng băng (`noise/ es/ ledger/ generation_record.py`) | **Được sửa** A-001, A-002, A-003, A-007, A-013, A-014 (và lỗi mới trong vùng này), **bắt buộc** theo giao thức chứng minh P-FROZEN (mục 2) |
| Tách repo | Repo 1 `hetero-es` = lõi + backend + web (refactor, thêm Postgres/OIDC/S3). Repo 2 `heteroes-minicloud` = hạ tầng 9 server, Dockerfile, compose, config, script EC2, minh chứng, báo cáo. Image build từ repo 1 ở commit được ghim |
| Yêu cầu đồ án | Làm **cả hai, lồng vào nhau**: mỗi mục đúng chữ đề (để chấm theo checklist), nội dung là HeteroES thật |
| Đăng nhập | **Keycloak thật, 2 chế độ**: cloud dùng OIDC (JWT, JWKS); desktop/local giữ đăng nhập cũ; thiết bị GPU giữ token thiết bị |
| Database | **PostgreSQL** (1 server: DB `heteroes`, `keycloak`, `studentdb`, `minicloud`); SQLite vẫn dùng cho desktop và test nhanh |
| Refactor backend | **Chia thành nhiều service** (cách an toàn: một codebase, nhiều entrypoint/container, chung Postgres, khóa trong DB; đi qua bước 3 lớp trước) |
| Giám sát | Cả 4: node-exporter + cAdvisor; `/metrics` của HeteroES; GPU của các worker; log tập trung Loki |
| Vai trò bản cloud | **Chạy song song**; lab thật ở nhà (`~/.local/share/heteroes-lab`, Cloudflare tunnel) **không đụng** |
| Tính toán | Worker cài bằng CLI trên máy GPU, nối vào cụm cloud. Cho phép thuê GPU (Vast.ai/RunPod/AWS…) nhưng **chủ dự án tự thuê**, Codex chỉ chuẩn bị |
| AWS | Tài khoản mới có 100 USD credit. Máy 8 GB RAM (`t3.large`, hoặc `m7i-flex.large` nếu gói Free chỉ cho loại "free-tier eligible"), vùng `ap-southeast-1` |
| Nhóm môn Cloud | Nguyễn Trần Hoàng Nhân **523H0164**, Khang **523H0145** (họ tên đầy đủ: chủ dự án điền vào `team.json`) |
| Hạn nộp | "Cứ làm đầy đủ": làm tuần tự A → B → C |
| GPU | Codex **được** dùng GPU 5070 Ti khi lab thật không có run/reservation |
| SSH | Codex **được** SSH vào 3060 của Thảo (`thao_nguyen@100.92.20.58`, đã cài key) cho nghiệm thu và làm worker cụm cloud. Mật khẩu sudo ở file riêng (mục 1) |
| GitHub repo 2 / Docker Hub / EC2 | **Chủ dự án tự tạo**; Codex chuẩn bị hết, chỉ push/deploy khi phát hiện tài nguyên đã có |
| Báo cáo | Codex làm minh chứng (script kiểm, ảnh chụp tự động, log) + **bản nháp docx** 5 chương; chủ dự án sửa và quay video |

## 0. Bước khởi đầu (Codex làm đầu tiên)

1. Tạo nhánh `review/fixes-2026-11` từ `main` trong repo 1. Commit đợt sắp xếp tài liệu đang dở (đã kiểm: chỉ đổi `docs/`,
   `runtime/docs/`, `README.md`) + `docs/REVIEW-PLAN.md` + `docs/review/FINDINGS-A.md`. **Không** commit
   `runtime/notebooks/researcher.ipynb` (xem A0) và `docs/evidence/` (xem A0).
2. Chép file kế hoạch này (`~/.claude/plans/t-i-mu-n-b-n-l-n-nifty-quiche.md`) vào
   `docs/plans/codex-2026-11-review-fixes-and-minicloud.md` trên cùng nhánh, rồi commit. Từ đây làm theo bản trong repo.
3. Ghi file riêng `~/.config/heteroes-private/codex-access.md` (quyền 0600, **ngoài repo**, không bao giờ commit hay in ra log).
   Nội dung:
   - Login SSH 3060: `thao_nguyen@100.92.20.58`, key đã cài.
   - Mật khẩu sudo (giống nhau trên mọi máy) do chủ dự án đưa trong lời nhắn khởi động.
   - Các lỗi WSL của 3060 (mục 1, luật 9).
   Kiểm ngay `ssh -o BatchMode=yes thao_nguyen@100.92.20.58 true`. Không vào được thì ghi blocker và làm phần không cần 3060.
   Chủ dự án bổ sung vào file này khi có: IP EC2 + đường dẫn khóa SSH, user Docker Hub, khóa Tailscale cho EC2.

## 1. Luật chạy tự động (Codex đọc trước tiên)

1. Đọc theo thứ tự: `AGENTS.md`, `docs/HANDOFF.md`, kế hoạch này, `docs/review/FINDINGS-A.md`, `~/projects/app_finding.md`,
   `~/.config/heteroes-private/codex-access.md`. Luật trong AGENTS.md vẫn có hiệu lực, trừ 2 chỗ được kế hoạch này nới:
   vùng đóng băng (chỉ khi có P-FROZEN) và SSH 3060.
2. **Không bao giờ dừng lại chờ câu trả lời.**
   - Việc chỉ chủ dự án làm được (mục 6): ghi vào mục "Việc của chủ dự án" trong `docs/HANDOFF.md`, kèm lệnh dán sẵn, rồi làm bước khác.
   - Bước hỏng: thử sửa có hệ thống tối đa 2 vòng. Vẫn hỏng thì revert phần dở, ghi finding, chuyển sang bước không phụ thuộc nó.
3. Thứ tự làm: A → B → C, trong mỗi phần làm theo số bước. Không làm C trước khi B xanh, vì image build từ repo 1.
4. Git:
   - Commit nhỏ, gom theo nhóm logic; **không** dòng `Co-Authored-By` (luật chủ dự án).
   - Merge vào `main` chỉ fast-forward; `git push origin --all` sau khi phần A xanh và sau khi phần B xanh.
   - Không force-push, không xóa nhánh remote, không push tag.
   - Repo 2: chỉ commit local; chỉ push khi `gh repo view Anakonkai01/heteroes-minicloud` thành công.
5. Test trước, code sau. Mỗi logic mới phải qua `scripts/mutation-check.py` trên bản sao trong scratch. Mutant còn sống thì
   thêm test, hoặc ghi rõ vì sao đó là mutant tương đương.
6. Bí mật:
   - Không in, không commit mật khẩu/token/khóa. Ghi vào file 0600 ngoài repo, hoặc vào `.env` đã nằm trong gitignore.
   - Truyền sudo qua stdin (`sudo -S`), không đặt mật khẩu trong tham số dòng lệnh.
   - Ảnh chụp không được lộ token/mật khẩu.
7. GPU:
   - Trước mỗi việc GPU chạy `python3 -I ~/.local/share/heteroes-lab/app/scripts/local-lab.py status`. Chỉ dùng GPU khi không có run và không có reservation.
   - Đặt `HETEROES_GPU_ACCEPTANCE=1`; test CPU thì đặt `CUDA_VISIBLE_DEVICES=''`.
   - Không đo throughput khi đang có việc GPU khác hoặc việc CPU nặng (kể cả `docker build`).
8. Lab thật: **chỉ** được `local-lab.py status`.
   - Không stop/restart/deploy.
   - Không dùng DB, thư mục state, hay cổng của nó: `127.0.0.1:8080`, `127.0.0.1:8081`, `100.110.165.40:8002`.
   - Không đổi trạng thái thiết bị trong lab thật (3060 đang REVOKED ở đó, cứ để nguyên).
9. SSH: chỉ tới `thao_nguyen@100.92.20.58`. Không SSH sang máy Nhựt, 1660S hay máy của Quang. Lưu ý với 3060:
   - Chạy GPU phải có `LD_LIBRARY_PATH=/usr/lib/wsl/lib`, vì có gói NVIDIA của Ubuntu làm torch segfault.
   - Không `apt install` gì liên quan NVIDIA.
   - WSL tự tắt khi rảnh, Windows không được ngủ.
   - Test deps trong `/tmp/heteroes-codex-testdeps-*` mất khi khởi động lại: cài lại bằng `pip --target`.
   - WSL và native Windows dùng chung một GPU, nên chạy lần lượt, không chạy song song.
10. Docker:
    - Project name luôn là `heteroes-minicloud`.
    - **Cấm** `docker rm -f $(docker ps -aq)`, `docker system prune -a`, `docker volume prune` (đề có ví dụ lệnh này, đừng làm theo).
    - Chỉ dọn của mình: `docker compose -p heteroes-minicloud down`.
11. Đĩa:
    - Trước nghiệm thu, `df -h /` phải còn ≥ 40 GB. Mỗi lần nghiệm thu local ghi ~1,4 GB vào `.scratch`; lưu biên bản xong thì xóa scratch của mình.
    - Không bao giờ dùng `/mnt/sekai`.
    - Giữ nguyên model `.scratch/strict-integer-20261025`.
12. Cấm `pkill -f` (nó giết luôn shell của mình); dừng tiến trình theo PID hoặc theo cổng.
13. Chạy `date` trước khi ghi ngày vào tài liệu.
14. Tiến độ:
    - Repo 1: cập nhật tại chỗ một mục "Tiến độ kế hoạch 2026-11" trong `docs/HANDOFF.md` sau mỗi bước.
    - Repo 2: cập nhật `PROGRESS.md`.
    - Viết tiếng Việt đơn giản cho chủ dự án; code và tài liệu kỹ thuật bằng tiếng Anh như AGENTS.md.
15. Phát hiện mới:
    - Ghi vào `FINDINGS-A.md` (lõi) hoặc `docs/review/FINDINGS-B.md` (ứng dụng), ID nối tiếp.
    - P0–P2: sửa ngay, kèm test. P3: sửa luôn nếu dưới khoảng 30 phút, không thì để backlog.
    - Lỗi mới trong vùng đóng băng: sửa theo P-FROZEN.
16. Evidence:
    - Đặt trong thư mục có ngày trên worktree của nhánh `evidence-archive`, có README với mục **What this does NOT show**.
    - Xong thì chạy `scripts/build-evidence-index.py` trên nhánh làm việc.
17. Điều kiện dừng duy nhất: làm xong hết. Nếu một chứng minh P-FROZEN thất bại mà không gỡ được thì revert đúng fix đó,
    để finding ở trạng thái mở, và làm tiếp phần còn lại.

## 2. Giao thức P-FROZEN (bắt buộc cho mọi sửa trong `noise/ es/ ledger/ generation_record.py`)

1. **Trước khi sửa**, tạo dấu vân tay "before" bằng code hiện tại (script để ở scratch, không đưa vào repo), trên CPU và trên
   GPU 5070 Ti. Gồm:
   - Hash nhiễu v1/v2 cho nhiều (seed, tensor, chunk).
   - Hash model sau `perturb_model_` (vài seed).
   - Hash model sau `apply_coefficients_` / `apply_es_update_`, với n = 1, 2, 3, 7, 32, 33, 512, nhiều alpha và hệ số.
   - Bản ghi chuyển trạng thái sổ cái của các test ledger hiện có.
   - Dùng model đồ chơi và một lát nhỏ của model `.scratch/strict-integer-20261025`.
2. Sửa xong, tạo bản "after" và so: **phải giống từng byte** với mọi đầu vào hợp lệ. Chỉ đầu vào không hợp lệ mới được đổi
   hành vi (bị từ chối).
3. Các test sau phải pass:
   - `tests/noise`, `tests/es`: CPU, GPU 5070 Ti, và 3060 qua `accept.py remote`.
   - Vector vàng §4.4, `scripts/check-noise-v2.py`.
   - Test ledger, test khôi phục coordinator.
4. Ghi vào evidence `<ngày>-frozen-fixes`: danh sách từng dòng đổi trong file đóng băng, lý do, before/after JSON, lệnh đã chạy.
   Cập nhật `runtime/docs/numerical-contract.md` và ADR liên quan (ADR-001/002).

## Phần A — Sửa phát hiện review (repo 1, nhánh `review/fixes-2026-11`)

### A0. Dọn dẹp
- Khôi phục `runtime/notebooks/researcher.ipynb` về bản đã commit (`git checkout --`). Bản đang sửa dở bị hỏng: dòng
  `from heteroes.sdk import ESConfig, ESTrainerfrom heteroes.sdk_lab import ...` là 2 dòng import bị dính vào nhau.
- Thư mục `docs/evidence/*` đang untracked: đã kiểm, toàn là log, `__pycache__`, `.ruff_cache`, và không có file nào trên
  `evidence-archive`. Chuyển sang `.scratch/leftover-docs-evidence-2026-10-29/`, không commit.
- Tạo `docs/review/FINDINGS-B.md` theo mẫu của FINDINGS-A từ `app_finding.md`:
  - B-001: Lab Server một khối, file phẳng (Q, P2).
  - B-002: route trộn API/logic/SQL (Q, P2).
  - B-003: `Store` gom mọi SQL, chỉ chạy SQLite (Q, P2).
  - B-Q1: vai trò server (D).
  - B-Q2: nơi lưu dữ liệu và bản sao lưu (D).
  Giữ nguyên ý của người bạn, ghi đề xuất sửa: phần B của kế hoạch này.

### A1. Bảo mật mạng (A-010 + mới A-020)
- **A-010** `runtime/src/heteroes/http_transport.py:439`: `HttpClient` dùng `build_opener(ProxyHandler({}))`, nên vẫn có
  handler redirect mặc định và gửi lại `Authorization` sang origin khác.
- **A-020 (mới, ghi vào FINDINGS-A, S/P2):** cùng lỗi ở mọi client gửi token bằng `urllib.request.urlopen` mặc định. `urlopen`
  còn tự dùng proxy theo biến môi trường. Các chỗ bị:
  - `product/agent_protocol.py:60` (token thiết bị gửi lên lab) và `:70`.
  - `product/worker_lab.py:44,59`, `product/worker_cli.py:717`, `product/cloud_sync.py:45`, `product/downloads.py:57`.
  - `sdk_lab.py:98,496`, `v3/lab_cli.py:38,57`, `study/prepare.py:63`.
- Cách sửa:
  - Module mới `runtime/src/heteroes/http_safety.py`, lấy `NoRedirect` sẵn có ở `product/connection.py:9` làm gốc.
    Cung cấp `opener(proxy: bool)` gồm `NoRedirect` + (`ProxyHandler({})` hoặc proxy hệ thống).
  - Đường worker/agent/coordinator: không proxy. SDK/`lab_cli` của nhà nghiên cứu: giữ proxy hệ thống, nhưng không redirect.
  - Gặp 3xx thì báo lỗi rõ ("máy chủ trả redirect tới <origin>, hãy dùng URL cuối") và không lộ token.
  - `connection.py` dùng lại module chung.
- Test: server A trả 302 sang server B ở cổng khác. Với từng điểm gọi kể trên, B không nhận được request nào và client ném lỗi.

### A2. Runtime ngoài vùng đóng băng
| ID | Chỗ sửa | Cách sửa | Test |
| --- | --- | --- | --- |
| A-015 | `coordinator.py` `run_generation`, nhánh `known` (~497-520) | So tập candidate (số lượng, seed namespace, antithetic, seed) với `ledger.list_candidates`; lệch thì `CoordinatorError` nêu rõ trường lệch | Chạy lại với `--candidates` khác → lỗi; giống → chạy tiếp |
| A-016 | `worker_api.py` `_submit_result` (~444-451); `coordinator.py:650` | Xóa nhánh texts không bao giờ chạy tới (chứng minh: `handle` đẩy list sang `_submit_texts`, dòng 274). Thêm `Ledger.count_audits(generation)` (chỉ đọc; file đóng băng → theo P-FROZEN), thay việc chọc `ledger._lock/_db` | Test hiện có + test `count_audits` |
| A-017 | `executor.py:284-288` | Mọi `Exception` trong lúc restore (không bắt `BaseException`) → `CandidateFailed(RESTORE_MISMATCH, ...)` để worker bị "poisoned" | Monkeypatch restore ném `RuntimeError`/`MemoryError` → RESTORE_MISMATCH |
| A-019 | `coordinator.py` `recover` (422-480), `run` | Lỗi thoát ra giữa lúc áp cập nhật → đánh dấu đối tượng "bẩn", `run()`/`recover()` từ chối (`CoordinatorError`: tạo Coordinator mới từ checkpoint). Thêm: `recover()` băm lại model, không tin `self.parent_sha256` | Tái hiện theo FINDINGS-A (khung `World` của `tests/ledger/test_coordinator_recovery.py`): trước sửa ra hash `1964a2da20…`; sau sửa bị từ chối, hoặc ra đúng `0b1951a8f5…` |
| A-008 | `noise/engine_v2_cuda.py` `enabled()` (đóng băng → P-FROZEN, phần log không đổi số) | Self-test GPU hỏng hoặc ném lỗi: ghi warning một lần và đưa cờ `noiseEngineGpu=false` + lý do vào `runtime_info` | Monkeypatch self-test hỏng; chạy `tests/noise/test_engine_v2_cuda.py` trên 3060 WSL + native |
| A-004 | `model/schema.py:54`, hợp đồng §2.5-2.6 | `SchemaEntry` kiểm: shape là tuple số nguyên ≥ 0, `numel == prod(shape)`, aliases là tuple đã sắp xếp, không trùng. Sửa chữ hợp đồng: bỏ hoặc đánh dấu chưa có `verify_model_matches`/`to_json`/`from_json` | Hash schema các fixture không đổi; entry sai thì bị từ chối |

### A3. Vùng đóng băng (theo P-FROZEN)
| ID | Chỗ sửa | Cách sửa |
| --- | --- | --- |
| A-001 | `es/update.py:127-136,250`; `es/cuda_ops.py:87` | Từ chối `alpha` nếu `np.float32(alpha)` không hữu hạn (tràn float32), **trước** byte ghi đầu tiên. Thêm kiểm trọng số sau cập nhật còn hữu hạn: đường CPU kiểm từng chunk trước khi ghi lại; đường GPU dùng một phép `isfinite` gộp, chỉ một lần sync ở cuối, ném `NonFiniteUpdateError`. Coordinator coi đây là lỗi chết: không `mark_applied`, run FAILED có lý do. Đo thời gian update trên Qwen GPU: chậm hơn > 1% thì chỉ giữ kiểm alpha + kiểm phía coordinator. Test tái hiện `alpha=1e39` (theo FINDINGS-A) |
| A-002 | `es/cuda_ops.py:105` | `acc * inv_n32` với `inv_n32 = float(np.float32(1) / np.float32(n_seeds))`, khớp đường CPU. **Trước khi sửa**, chạy trên GPU (5070 Ti và 3060): so `acc / n` với `acc * inv_n32` từng bit, n = 1..4096, tensor ngẫu nhiên → phải trùng 100%. Sửa chú thích "CUDA's division by a scalar" trong `update.py` |
| A-003 | `es/update.py` vs `es/cuda_ops.py` | Chuyển khối kiểm seed/độ dài/no-op dùng chung sang `es/checks.py`, giữ nguyên kiểu lỗi và câu báo. Bảng đầu vào sai cho ra lỗi giống hệt ở cả 2 đường |
| A-007 | `es/perturb.py` `perturb_model_`; `noise/contracts.py` `ChunkNoiseAddress` | Cùng luật seed như update: số nguyên thật (không bool/float/str), ≥ 0; `chunk_index` nguyên ≥ 0. Giữ chủ ý "engine không giới hạn 2^53" (giới hạn đó chỉ ở manifest) |
| A-013 | `ledger/ledger.py:1051` `record_membership` | Thêm `BEGIN IMMEDIATE` như `lease`/`submit_result`. Test: 2 đối tượng `Ledger` cùng file + barrier → bên thứ hai trả `False`, không phải `LedgerError` |
| A-014 | `ledger/ledger.py:783` `_charged_attempts`, `:1113` `release_worker` | Luật mới: attempt không bị tính vì worker đang bị cách ly thì **vẫn không bị tính** sau `release_worker`. Ràng buộc: file ledger cũ vẫn mở và resume được (nếu thêm bảng/cột thì migrate khi mở); ledger không có lần release nào cho số đếm giống hệt cũ; ca tái hiện cho `('OPEN', charged=1)` sau release. Bổ sung ADR-002 |

### A4. Nghiệm thu (A-011, A-012)
- **A-011** (`acceptance/core.py:181`, `registry.py`):
  - Check bằng pytest: đọc dòng tổng kết của pytest; `Check` có thêm `min_passed`/`max_skipped`. Suite GPU: `max_skipped=0`,
    `min_passed` lấy theo lần chạy tốt gần nhất.
  - Thiếu dòng tổng kết → FAIL.
  - Biên bản lưu `counts`, dòng tổng kết, 50 dòng log cuối, sha256 của log, và đường dẫn log tương đối trong repo (không trỏ ra repo cũ).
- **A-012** (`core.py:117-130`):
  - `source_tree` loại thêm `runtime/docs/**` và các `*.md` ở gốc repo (README, AGENTS, CLAUDE), cả ở danh sách `ls-tree` lẫn `git status`.
  - Test: sửa file trong `runtime/docs` → src id không đổi; sửa `runtime/src` → src id đổi.
  - Sửa câu tương ứng trong HANDOFF/REVIEW-GUIDE.
- Sửa chữ gate `M5.release`: đã deploy `10457f9a` ngày 2026-10-28; deploy lại là việc của chủ dự án.

### A5. Tài liệu trả lời người bạn
- Viết `docs/design/lab-server-architecture.md` (tiếng Anh, có mục tóm tắt tiếng Việt), trả lời 2 câu hỏi:
  - **B-Q1, vai trò hiện nay** (cùng một tiến trình `backend.server`): web tĩnh, REST API người dùng, cổng thiết bị
    (enroll/poll/telemetry/commands), bộ lập lịch (luồng `store.dispatch`), lưu trữ (recovery points, upload/download
    ticket, `local_storage`), sao lưu metadata (`metadata_backup.backup_loop`), stream SSE, thông báo.
    Phía trước là Caddy (`backend/deployment.py:caddyfile`) và Cloudflare tunnel.
  - **B-Q2, dữ liệu nằm đâu**:
    - `product.sqlite` (người dùng, workspace, run, thiết bị, assignment, telemetry…).
    - Sổ cái SQLite + checkpoint của từng run nằm ở máy coordinator.
    - Recovery objects ở `storageDirectory`; bản sao metadata ở `metadataStorageDirectory`; installer ở `downloads`.
    - Evidence ở nhánh `evidence-archive`.
- Phần B cập nhật lại tài liệu này theo kiến trúc mới.

### A6. Kiểm và chốt phần A
1. Chạy `scripts/check-all.sh .scratch/checks-<ngày>-partA`. Chạy test backend và test runtime CPU (lệnh trong AGENTS.md).
   Chạy mutation check cho code mới.
2. GPU 5070 Ti: `tests/noise`, `tests/es`, `tests/eval` (Qwen thật).
3. Nghiệm thu đầy đủ, theo thứ tự:
   - `accept.py run cpu`.
   - `HETEROES_GPU_ACCEPTANCE=1 python3 scripts/accept.py run gpu perf faults package mutation --keep`.
   - `accept.py remote 3060-wsl gpu perf --keep`, **sau đó mới** `accept.py remote 3060-native gpu --keep`.
   - `accept.py report --write`.
   - Throughput phải trên mức sàn (`acceptance/golden/throughput.json`).
4. Commit biên bản. Evidence `<ngày>-review-fixes` (P-FROZEN + before/after). Cập nhật HANDOFF, FINDINGS (cột trạng thái).
5. Fast-forward `main`, rồi `git push origin --all`. **Không** deploy lab thật (việc của chủ dự án, ghi vào mục 6).

## Phần B — Backend chia lớp và tách nhiều service (repo 1, nhánh `feat/cloud-services` từ `main` sau A)

Hiện trạng đã đo:
- `backend/` có 46 file nguồn (~7 800 dòng), ~351 lời gọi `.execute(` rải ở 15 file, 69 chỗ cú pháp riêng của SQLite
  (`json_extract`, `INSERT OR`, `PRAGMA`, `BEGIN IMMEDIATE`, `rowid`).
- Mọi truy cập DB đi qua `Store.db()` với `RLock` của tiến trình (`store.py:56`). Mỗi DB chỉ có một tiến trình ghi (`writer_lock.py`).
- Có 363 test backend.
- `scripts/build-server-profile.py:49` chỉ glob `backend/*.py` (thư mục con sẽ bị **thiếu** khi đóng gói desktop).

### B1. Kiểm kê trước khi tách
- Bảng **trạng thái trong bộ nhớ**: `Throttle` (đăng nhập/đăng ký), `LiveStreams`, `_Upload` của `local_storage`, thread của
  `RecoveryStorage.verify_background`, `metadata_backup`, `writer_lock`, `AgentRuntime` (đã kiểm sơ bộ: chủ yếu đọc DB).
  Mỗi mục quyết định: chuyển vào DB, giao cho Keycloak, hay giữ trong một service một bản sao.
- Bảng **route → service**: khoảng 90 route `/api/v1/...`, cộng `/downloads/manifest.json` và route web. Mỗi route thuộc
  đúng một service.
- Ghi cả hai vào `docs/design/lab-server-architecture.md`.

### B2. Chia 3 lớp, không đổi hành vi
Bố cục đích:
```
backend/
  api/           # router FastAPI: đọc request, gọi service, đổi lỗi → HTTP. Không SQL.
  services/      # logic nghiệp vụ (accounts, workspaces, experiments, devices, scheduling, storage, studies, notifications, operations)
  repositories/  # toàn bộ SQL, một lớp cho mỗi nhóm dữ liệu
  db/            # engine, transaction, khác biệt SQLite/Postgres, schema (migrations SQLite + DDL Postgres)
  core/          # config, errors, constants, security (dependency xác thực user/thiết bị)
  apps/          # create_app(service=...), entrypoint cho từng service
```
- Làm theo thứ tự miền: accounts/auth → workspaces → experiments/history/queue → templates/notifications →
  devices + agent_* → studies/models/qualification → storage → operations/platform.
- Mỗi bước giữ module cũ làm **shim re-export**: 363 test phải xanh **mà không sửa test**.
- `Store` thu nhỏ dần thành lớp mặt tiền mỏng.

### B3. Lớp DB chạy được cả SQLite và Postgres
- SQLAlchemy 2 Core chỉ dùng cho engine, pool, transaction. SQL giữ dạng `text()` với tham số có tên (đổi `?` → `:name`
  một cách máy móc).
- Câu DML viết cho chạy được cả hai: `INSERT ... ON CONFLICT`, `RETURNING`.
- JSON: parse bằng Python, hoặc qua helper theo từng dialect. Thay `rowid` bằng cột thứ tự rõ ràng.
- Driver psycopg 3, import lười để desktop không cần.
- `db.transaction(write=True)`:
  - SQLite: `RLock` + `BEGIN IMMEDIATE` (như cũ).
  - Postgres: `BEGIN` + `SELECT pg_advisory_xact_lock(<LAB_WRITE_LOCK>)`. Giữ đúng ngữ nghĩa "một người ghi tại một thời
    điểm", kể cả giữa các container.
- Schema:
  - SQLite giữ `migrations.py` (DB desktop và lab thật cũ vẫn nâng cấp được).
  - Postgres: `db/postgres_schema.sql` + bảng phiên bản.
  - Một test so sánh 2 schema: cùng bảng, cột, khóa chính, unique.
- Phụ thuộc: cập nhật `backend/requirements*.txt` và lock. Desktop profile chỉ thêm SQLAlchemy.
- Kiểm: script `scripts/check-backend-postgres.sh` chạy `postgres:17-alpine` tạm trên cổng localhost ngẫu nhiên (không dùng
  cổng của lab thật), rồi chạy **toàn bộ** test backend với `HETEROES_TEST_DATABASE_URL`. Phải xanh 100% trên cả SQLite và Postgres.
- Thêm test đua trên Postgres: 2 tiến trình cùng giành một thiết bị/lease → đúng một bên thắng.

### B4. Tách service (cùng một image)
| Service | Route | Bản sao |
| --- | --- | --- |
| `api` | người dùng: auth/session, workspace, experiments, history, templates, notifications, inventory, studies/models phía người dùng, router đồ án (B8) | 2 (không giữ trạng thái) |
| `devices` | `/api/v1/device/*` (enroll, poll, telemetry, commands, contribution, transfers), pairing | 1 (có thể 2 nếu B1 cho phép) |
| `storage` | recovery points, local-storage, public-upload, cloud-downloads, artifacts, datasets uploads; sao lưu metadata | 1 |
| `scheduler` | không route công khai (chỉ `/healthz`, `/metrics`); chạy vòng `dispatch` + việc nền | 1 bản đang chạy + bản chờ (khóa `pg_try_advisory_lock`) |
| `all` | gộp hết như hôm nay (desktop, `local-lab.py`, SQLite) | 1 |

- Entrypoint `python -m backend.apps.<service>`; `create_app(dispatch=False)` đã có sẵn.
- Test bắt buộc: hợp các bảng route của `api`/`devices`/`storage` **bằng đúng** bảng route của `all` (method + path),
  không route nào trùng.
- Xuất bảng route: `python -m backend.apps.routes --json`. Repo 2 sinh/kiểm cấu hình nginx từ bảng này.
- Sao lưu ở chế độ Postgres: `pg_dump` định kỳ vào bucket MinIO `heteroes-backups`, kèm script khôi phục và một lần diễn tập.
- Chế độ `all` + SQLite phải giống hệt trước: `check-all.sh` và `build-apps.sh --check` xanh.

### B5. Đăng nhập OIDC (Keycloak), `HETEROES_AUTH_MODE=local|oidc` (mặc định `local`)
- Backend:
  - Kiểm JWT RS256 bằng PyJWT + cryptography: `iss` = issuer công khai, `aud`/`azp` = `heteroes-web`, `exp`/`nbf` lệch tối đa 30 s.
  - JWKS lấy qua URL nội bộ, có cache, tải lại khi gặp `kid` lạ, không theo redirect (dùng `http_safety` hoặc httpx với
    `follow_redirects=False`). Từ chối `alg=none`/HS256.
  - Người dùng: `sub` → dòng user `kc:<sub>`, username lấy từ `preferred_username`. Role realm `lab-admin` = quản trị nền tảng.
    Người khác vào trạng thái chờ duyệt như luồng hiện có.
  - Ở chế độ oidc, `/auth/login|register|password|revoke-other-sessions` trả 404 kèm hướng dẫn. `/auth/session` dùng JWT.
  - Token thiết bị giữ nguyên.
- Frontend:
  - Dùng `oidc-client-ts` (Authorization Code + PKCE). Cấu hình đọc từ `/config.json` do container web phục vụ, để một bản
    build chạy được cả local và EC2.
  - Nút "Đăng nhập bằng HeteroES ID"; logout qua end-session; token giữ trong bộ nhớ, tự gia hạn.
  - Chuỗi i18n vi/en (`check-i18n.mjs`). Các `check-web-*.mjs` ở chế độ local vẫn xanh.
- Lưu ý: PKCE cần secure context. Chạy được trên `http://localhost`, **không** chạy trên `http://<public-ip>` → EC2 phải có HTTPS (C7).
- Test: khóa RSA sinh tại chỗ + JWKS giả. Các ca: hợp lệ, hết hạn, sai iss, sai aud, `kid` lạ → tải lại, `alg` sai, JWKS trả redirect.

### B6. Lưu trữ S3/MinIO
- Hồi sinh `S3Backend` từ `git show 8226f32b^:backend/cloud_storage.py`: presigned multipart, inventory, manifest.
  Đặt vào `backend/storage/s3_backend.py`, `storageMode: "s3"`.
- Bỏ các chốt riêng của R2: `exclusiveAccountConfirmed`, bắt buộc HTTPS (cho phép http với endpoint nội bộ/riêng), đếm request class A/B.
- Dùng 2 endpoint:
  - Nội bộ, cho thao tác của server.
  - Phía thiết bị, để ký URL. Endpoint này phải là đường riêng (Tailscale), giữ đúng luật "dữ liệu lớn chỉ qua đường riêng" của `caddyfile`.
- Mở rộng `_app_from_config` (hiện chỉ nhận `storageMode` local). `LocalBackend` vẫn là mặc định.
- Bộ test storage chạy trên cả 2 backend (MinIO tạm trong Docker).

### B7. Quan sát được
- Mỗi service có `/healthz` (còn sống), `/readyz` (DB + storage), `/metrics` (`prometheus_client`):
  - HTTP: số request và độ trễ theo **mẫu route**, không theo path thô.
  - Số liệu nghiệp vụ, chỉ `scheduler` xuất để không trùng; tính lúc scrape từ DB:
    - Thiết bị theo trạng thái, thiết bị online.
    - GPU từng thiết bị (% dùng, VRAM, nhiệt độ, công suất), lấy trường từ `heteroes/product/telemetry.py`.
    - Run theo trạng thái, độ dài hàng đợi, số thế hệ xong, lỗi candidate theo loại, dung lượng storage/quota.
- Log JSON ra stdout, mỗi request một dòng: ts, level, service, method, route, status, duration_ms, request_id.
  Test: request có token/mật khẩu thì log không chứa chúng.

### B8. Router đồ án (`HETEROES_COURSE_DEMO=1`, mặc định tắt, chỉ trong `api`)
- `GET /hello` → `{"message":"Hello from App Server!"}`.
- `GET /secure`: kiểm token của client `flask-app` trong realm; có token → `{"message":"Secure resource OK","preferred_username":...}`, không có → 401.
- `GET /student`: đọc `students.json` được mount vào.
- `GET /students-db`: đọc `studentdb.students` qua `HETEROES_COURSE_STUDENTDB_URL`, role chỉ đọc.
- Có test.

### B9. Cấu hình, đóng gói, gỡ shim
- Cấu hình qua biến môi trường cho container, đặt chồng lên thư mục config riêng: `HETEROES_SERVICE`,
  `HETEROES_DATABASE_URL`, `HETEROES_AUTH_MODE`, `HETEROES_OIDC_ISSUER`, `HETEROES_OIDC_JWKS_URL`, `HETEROES_STORAGE_*`,
  `HETEROES_PUBLIC_URL`. Bí mật chỉ qua env hoặc secret file, không ghi log.
- Sửa `scripts/build-server-profile.py` (dùng `rglob`, bỏ `tests`) và `check-source-packages.py`.
- Gỡ shim: chỉ sửa dòng import trong test, có script diff chứng minh mọi dòng đổi đều là `import`/`from`.

### B10. Kiểm và chốt phần B
- Chạy:
  - `check-all.sh`.
  - Test backend trên SQLite và Postgres.
  - `scripts/build-apps.sh --check .scratch/fresh-linux-check` (đóng gói desktop).
  - Kiểm web, mutation check (xác thực JWT, khóa transaction, bảng route, S3).
- Nghiệm thu đủ 3 máy như A6 (backend đổi nên hash nguồn đổi).
- Cập nhật `lab-server-architecture.md`, đánh dấu B-001..B-003 đã sửa.
- Fast-forward `main` + push. Ghi `HETEROES_REF` = commit này cho repo 2.

## Phần C — Repo `heteroes-minicloud`

### C1. Bố cục (9 thư mục theo đề + 2 thư mục riêng của HeteroES)
```
heteroes-minicloud/
  README.md  AGENTS.md  PROGRESS.md  HETEROES_REF  team.json  .env.example  .gitignore(.env, vendor/, out/)
  docker-compose.yml   compose.local.yml   compose.ec2.yml
  web-frontend-server/            # Dockerfile nhiều giai đoạn: build SPA HeteroES từ vendor/heteroes; nginx; html/ (trang chủ + blog)
  application-backend-server/     # Dockerfile image backend HeteroES (4 service theo lệnh chạy), students.json, entrypoint
  relational-database-server/     # init/*.sql: role + DB heteroes, keycloak, studentdb, minicloud; demo-crud.sql
  authentication-identity-server/ # realm-import/realm_523h0164.json (không chứa bí mật) + bootstrap kcadm
  object-storage-server/          # init bằng mc: bucket, policy
  internal-dns-server/            # named.conf.*, db.cloud.local.template, entrypoint render theo dải mạng
  monitoring-prometheus-server/   # prometheus.yml, rules
  monitoring-grafana-dashboard-server/ # provisioning: datasource Prometheus+Loki, dashboard JSON
  logging-loki-server/            # loki.yaml, alloy config (server số 8, phần log)
  api-gateway-proxy-server/       # nginx.conf (sinh/kiểm từ bảng route), cấu hình TLS
  compute-coordinator-server/     # Dockerfile coordinator CPU (CLI worker HeteroES, torch CPU)
  scripts/  fetch-heteroes.sh up.sh down.sh bootstrap.sh check-minicloud.sh screenshots.mjs gen-gateway-conf.py push-images.sh deploy-ec2.sh
  docs/report/ (nguồn + build → out/BaoCao-Cuoi-Ky-Cloud.docx), docs/video-script.md, docs/rent-gpu-worker.md
  evidence/<ngày>-<local|ec2>/
```
- `fetch-heteroes.sh` clone/checkout đúng `HETEROES_REF` vào `vendor/heteroes`, rồi kiểm SHA.
- Ghim mọi image theo tag (không dùng `latest`). Mọi service: `restart: unless-stopped`, healthcheck,
  `depends_on: condition: service_healthy`, volume có tên cho DB/MinIO/Grafana/Prometheus/Loki.
- `team.json`: Nhân 523H0164, Khang 523H0145. Các trường chưa biết (họ tên Khang, ngày sinh, GPA…) ghi rõ là `"mẫu"`
  để chủ dự án sửa. Không bịa thông tin về người thật.

### C2. Mạng và cổng
- Dải mạng `cloud-net`:
  - EC2: `10.10.10.0/24`, trùng ví dụ DNS của đề, nên `web-frontend-server.cloud.local` trả đúng `10.10.10.10` thật.
  - Local: `10.77.10.0/24`, vì `eno1` của máy 5070 Ti **đang dùng `10.10.10.0/24`**; trùng dải sẽ làm hỏng mạng cáp.
  - Đặt qua `CLOUD_NET_SUBNET`/`CLOUD_NET_PREFIX`; zone DNS được render từ prefix.
- Bảng cổng:

| Container (IP .x) | Alias (cho lệnh ping của đề) | Cổng EC2 | Cổng local |
| --- | --- | --- | --- |
| api-gateway-proxy-server (.2) | proxy | 80, 443 | 18000 |
| web-frontend-server-1 (.10), -2 (.11) | web, web-frontend-server / web2 | 8080 (bản 1) | 18080 |
| application-backend-server-1 (.20), -2 (.21) (service `api`) | app-server, app-backend | 8085→8081 | 18085 |
| heteroes-devices (.22), heteroes-storage (.23), heteroes-scheduler (.24) | – | – | – |
| relational-database-server (.30) | db, postgres | 127.0.0.1:5432 | 127.0.0.1:15432 |
| authentication-identity-server (.40) | keycloak | 8081→8080 | 18081 |
| object-storage-server (.50) | minio | 9000, 9001 | 19000, 19001 |
| internal-dns-server (.53) | dns-server | 1053/udp | 11053/udp |
| monitoring-prometheus-server (.60) | prometheus | 9090 | 19090 |
| monitoring-node-exporter-server (.61), cadvisor (.62) | node-exporter, cadvisor | 9100 / – | 19100 / – |
| monitoring-grafana-dashboard-server (.70) | grafana | 3000 | 13000 |
| logging-loki-server (.71), logging-alloy (.72) | loki | – | – |
| compute-coordinator-server (.80) | coordinator | chỉ IP Tailscale | IP Tailscale `100.110.165.40`, cổng khác lab thật |

- Security group của EC2:
  - Mở công khai: 80, 443.
  - Chỉ IP của chủ dự án (/32): 22 và các cổng console của đề (3000, 8080, 8081, 8085, 9001, 9090, 1053/udp).
  - DB và MinIO API không công khai.
- Lưu ý: cổng Docker publish đi vòng qua ufw, nên phải dựa vào security group, hoặc bind `127.0.0.1`.

### C3. Từng server: vai trò HeteroES + demo cơ bản + mở rộng
- **Web (×2):**
  - `/` là trang chủ tĩnh có đúng chữ "MyMiniCloud – Home" (kèm "HeteroES on MiniCloud"), có danh sách 3 bài blog và nút "Mở HeteroES Lab".
  - `/blog/` có tiêu đề "MyMiniCloud Blog" và `blog1..3.html`. Mỗi bài có hình tự vẽ (SVG/PNG, không lấy ảnh có bản quyền) và link về trang chủ.
    Chủ đề: ES không cần backprop; tái lập từng bit trên GPU khác loại; đưa HeteroES lên MiniCloud.
    Nội dung theo "Project claim" trong AGENTS.md: không nói "ES học được"; số liệu lấy từ HANDOFF (vd. 10 075 token/s ≈ 72,8% vLLM).
  - SPA HeteroES ở `/lab/`: Vite `base` + router basename qua biến build; API vẫn gọi tuyệt đối `/api/v1`.
  - `/metrics`: text Prometheus `heteroes_web_up 1` (để target `web` lên UP).
  - Header `X-Served-By: $hostname`; trang `/lb-test` in tên container.
- **App (service `api` ×2 + devices + storage + scheduler):** HeteroES thật cộng router đồ án (B8).
- **DB Postgres:** DB `heteroes`, `keycloak`, `studentdb` (bảng `students(id, student_id, fullname, dob, major)` ≥ 3 dòng
  + `demo-crud.sql`), `minicloud` (bảng `notes`, dòng 'Hello from PostgreSQL!'). Mỗi DB một role riêng.
- **Auth Keycloak:**
  - Chạy `start` với `KC_DB=postgres`, `KC_HTTP_RELATIVE_PATH=/auth`, `KC_PROXY_HEADERS=xforwarded`,
    `KC_HOSTNAME=<URL công khai>/auth`, `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true`, `KC_HEALTH_ENABLED`, `KC_METRICS_ENABLED`; giới hạn heap.
  - Realm `realm_523h0164`, nạp khi khởi động:
    - Client `heteroes-web` (public, PKCE S256, redirect cho localhost và EC2).
    - Client `flask-app` (public, bật direct access grants để demo token bằng curl).
    - User `sv01` (Nhân, `lab-admin`) và `sv02` (Khang).
    - Mật khẩu do `bootstrap.sh` đặt qua kcadm, lấy từ `.env`. Bật brute-force detection.
  - Backend kiểm `iss` bằng URL công khai nhưng lấy JWKS qua `http://keycloak:8080/auth/...`.
- **MinIO:**
  - Bucket riêng tư của HeteroES: `heteroes-recovery`, `heteroes-datasets`, `heteroes-backups`.
  - Bucket theo đề: `demo` (index.html), `profile-pics` (`avatar.jpg`, cho đọc ẩn danh, URL công khai mở được), `documents` (PDF báo cáo).
  - Ghim tag image và **kiểm** console còn tạo bucket/upload được không (bản community từ giữa 2025 cắt bớt console).
    Nếu thiếu thì tạo bucket/policy bằng `mc` và demo bằng object browser.
- **DNS bind9:**
  - Zone `cloud.local` có bản ghi thật cho mọi container, cộng các bản ghi đề yêu cầu: `app-backend` → `.20` (chính là
    api-1), `minio`, `keycloak`.
  - Chỉ cho đệ quy trong mạng nội bộ (không làm open resolver).
  - Container demo khai `dns: [<prefix>.53]`; DNS nhúng của Docker vẫn phân giải tên service.
- **Prometheus:** job `node`, `cadvisor`, `web` (cả 2 bản), `heteroes` (4 service), `keycloak`, `minio`.
  `/metrics` không mở ra gateway công khai.
- **Grafana + Loki:**
  - Provisioning datasource; datasource URL `http://prometheus:9090` (đúng tên đề dùng).
  - Dashboard:
    - "Node Exporter Full" (JSON vendored).
    - "System Health of 523H0164" và bản cho 523H0145, mỗi bảng ≥ 3 panel: CPU % từ `node_cpu_seconds_total`, bộ nhớ từ
      `node_memory_MemAvailable_bytes`, mạng từ `node_network_receive_bytes_total`.
    - "HeteroES Lab": thiết bị, GPU từng worker, run, request.
    - "Logs" từ Loki.
  - Log đi qua Grafana Alloy (Promtail đã bị khai tử), đọc `docker.sock` chế độ chỉ đọc, giữ 7 ngày.
  - Phục vụ ở `/grafana/` qua gateway và cổng 3000.
- **Gateway nginx:**
  - `upstream web_pool` và `api_pool` round robin; header `X-Upstream` để demo cân bằng tải.
  - Route theo bảng route của B4: `/api/v1/device/*` → devices, nhóm storage → storage, còn lại `/api/v1/` → api_pool.
  - `/api/` strip → api (route đồ án); `/student/` → `api_pool/student`; `/auth/` → keycloak (302 sang trang login); `/grafana/`.
  - Chặn `/metrics` từ ngoài. Giới hạn body như `caddyfile()` (3 MB, riêng `public-upload` 64 MiB). Bulk path trả 403
    "Private LAN/Tailscale transfer required" giống hệt `caddyfile()`. Header `nosniff`, `no-referrer`.
  - SSE: `proxy_buffering off`, `proxy_read_timeout 3600s`.
  - Một server block "compute" (cổng riêng) chỉ cho các đường điều khiển `/v1/health /v1/job /v1/leases /v1/heartbeats
    /v1/results /v1/failures /v1/updates/*` tới coordinator.
  - Script so cấu hình nginx với bảng route và với luật `caddyfile()`.

### C4. Bảng đối chiếu checklist chấm điểm (mỗi dòng = một check trong `check-minicloud.sh`)
| # | Đề | Cách đáp ứng | Lệnh kiểm |
| --- | --- | --- | --- |
| 1 | Web 200 + nội dung | trang chủ/blog | `curl -I :8080/`, `:8080/blog/`, grep chữ |
| 2 | App `/hello` trực tiếp + qua proxy | router đồ án | `curl :8085/hello` == `curl /api/hello` |
| 3 | DB truy vấn | `minicloud.notes` | `docker exec relational-database-server psql -U postgres -c '\l'` + SELECT notes (đề dùng mysql; báo cáo giải thích chọn Postgres) |
| 4 | Keycloak login, tạo user | admin console | ảnh chụp + kcadm liệt kê user |
| 5 | MinIO upload | bucket `demo` | `mc ls` + ảnh |
| 6 | DNS | bind9 | `dig @127.0.0.1 -p 1053 web-frontend-server.cloud.local +short` |
| 7 | Prometheus target UP | node-exporter | API `/api/v1/targets` mọi target `up` |
| 8 | Grafana dashboard | provisioning | API Grafana liệt kê dashboard + ảnh |
| 9 | Proxy 3 đường | nginx | `/` 200, `/api/hello` JSON, `/auth/` 302 |
| 10 | Ping mọi server | alias | `docker run --rm --network cloud-net busybox ping -c 3 <web, app-server, db, keycloak, minio, prometheus, grafana, dns-server>` |
| M1 | Blog 3 bài | blog1..3 | curl 3 trang + link về trang chủ + ảnh |
| M2 | `/student` JSON | students.json | `curl /api/student` |
| M3 | studentdb CRUD | bảng students | `psql -f demo-crud.sql`, `curl /api/students-db` |
| M4 | Realm + client + token | `realm_523h0164`, `flask-app` | password grant lấy token → `curl /api/secure` 200; không token → 401 |
| M5 | profile-pics + documents | MinIO | URL công khai avatar 200; PDF có trong `documents` |
| M6 | Bản ghi DNS | zone | `dig app-backend/minio/keycloak.cloud.local` |
| M7 | Target `web` UP | `/metrics` tĩnh | targets API |
| M8 | Dashboard System Health | provisioning | API + ảnh |
| M9 | Route `/student/` | nginx | `curl /student/` |
| M10 | Round robin 2 web | upstream | 6 request `/lb-test` luân phiên `-1/-2` |
| H1–H6 | Phần HeteroES | xem C6 | đăng nhập Keycloak vào `/lab/`; ghép thiết bị; run trọn vẹn; recovery points nằm trong MinIO; dashboard GPU; tắt api-1 mà request vẫn chạy; tắt scheduler-1 thì bản chờ tiếp quản; `docker kill` → tự khởi động lại |

- Kết quả ghi vào `evidence/<ngày>-<host>/`:
  - `checks.json` (PASS/FAIL từng dòng), output từng lệnh.
  - `docker compose ps`, danh sách image kèm digest.
  - README có mục "What this does NOT show".

### C5. Image và Docker Hub
- Các image:
  - `heteroes-web`, `heteroes-backend` (một image cho 4 service), `heteroes-coordinator-cpu` (torch bản CPU qua
    `--index-url https://download.pytorch.org/whl/cpu`).
  - `heteroes-gateway` và `heteroes-dns` (đã bake cấu hình, để EC2 chỉ cần pull).
- Build linux/amd64, tag `<user>/heteroes-<tên>:<HETEROES_REF ngắn>` và `:course`.
- `push-images.sh` chỉ chạy khi `docker login` đã có (mục 6).
- Ghi chú cho chủ dự án: image backend/coordinator chứa mã nguồn Python đọc được. Nếu muốn giữ kín thì chỉ để public
  `web`/`gateway`/`dns` (đề chỉ cần ≥ 1 image).

### C6. Chạy trọn vẹn ở nhà (bắt buộc, không cần chủ dự án)
1. `fetch-heteroes.sh`, `up.sh local`, `bootstrap.sh`, `check-minicloud.sh local`: các check đề phải PASS hết.
2. Ghép thiết bị:
   - Container coordinator CPU tự enroll bằng pairing code mà `bootstrap.sh` tạo qua API admin.
   - 3060 WSL qua SSH, theo đường headless có sẵn: `python -m heteroes.product.agent enroll|run`, thư mục state riêng, code đúng `HETEROES_REF`.
   - 5070 Ti chỉ là agent thứ hai (thư mục, cổng riêng) khi lab thật rảnh, và chạy ngắn.
3. Run demo:
   - Thử trước run Recipe v3 **không strict** với coordinator CPU (profile `coordinator-cpu-v3`, `product/cpu_coordinator.py`).
   - Nếu sản phẩm bắt coordinator GPU (luật D1 cho strict): coordinator = 5070 Ti (agent trên máy host, không trong
     Docker), worker = 3060, run strict.
   - Vài thế hệ là đủ. Không chạy dài để "chứng minh ES học" (Project claim).
4. Kiểm H1–H6. Chụp ảnh bằng `screenshots.mjs` (Playwright đã có trong repo 1): trang chủ, 3 bài blog, login Keycloak → Lab,
   dashboard run, realm Keycloak, bucket MinIO, target Prometheus, các dashboard Grafana, luân phiên LB.

### C7. EC2 (khi chủ dự án đã làm O3; chưa có thì chuẩn bị xong rồi chuyển sang C8)
- Máy: Ubuntu 24.04 x86_64, 8 GB RAM (`t3.large`, hoặc `m7i-flex.large` nếu gói Free giới hạn loại máy), gp3 40 GB,
  vùng `ap-southeast-1`. Khoảng 0,1 USD/giờ → 100 USD ≈ 900 giờ. Tắt máy khi không dùng; IPv4 công khai cũng tính tiền.
- `deploy-ec2.sh` (đọc IP + khóa trong file riêng), theo thứ tự:
  1. SSH vào; cài Docker Engine + plugin compose từ repo apt chính thức.
  2. rsync repo 2 (trừ `.env`, `vendor`); ghi `.env` từ file riêng.
  3. `docker compose pull`. Chưa push được lên Docker Hub thì `docker save | ssh docker load`.
  4. `up`, `bootstrap`.
  5. HTTPS: tên miền `<ip-gạch-ngang>.sslip.io` + Let's Encrypt (certbot webroot qua gateway); dự phòng chứng chỉ tự ký
     (ghi rõ cảnh báo trình duyệt). HTTP vẫn giữ cho các lệnh curl của đề.
  6. `check-minicloud.sh ec2`, kéo evidence về.
- Có khóa Tailscale (O4) thì cài Tailscale trên EC2, để coordinator/MinIO có đường riêng cho worker GPU. Khi đó chạy lại C6
  bước 2–3 với control plane trên EC2. Không có khóa thì demo EC2 = 9 server + control plane; run trọn vẹn đã có ở C6.
- Agent phải được cấu hình URL https cuối cùng (A-010/A-020 không cho theo redirect).

### C8. Báo cáo và video
- `docs/report/` dựng `out/BaoCao-Cuoi-Ky-Cloud.docx` bằng python-docx (có thể mượn khung `~/projects/bao-cao/*/src/build.py`):
  - Chương 1: giới thiệu, mô hình 9 server ↔ thành phần HeteroES.
  - Chương 2: sơ đồ mạng (IP, alias), luồng request (trình duyệt → gateway → web/api → DB/Keycloak/MinIO; worker GPU →
    devices/coordinator), luồng giám sát/log.
  - Chương 3: Dockerfile, compose, config tiêu biểu.
  - Chương 4: ảnh + output từng check.
  - Chương 5: ưu điểm, khó khăn, hướng mở rộng (vd. 2 bản api, khóa advisory, failover scheduler, GPU thuê).
  - Phụ lục: link Docker Hub/GitHub/video (để placeholder cho tới khi có O1/O2/O7), log, **bảng "đã làm được bao nhiêu
    phần mở rộng"** (đề bắt buộc ghi).
- `docs/video-script.md`: kịch bản 5–8 phút theo đúng thứ tự checklist.
- `docs/rent-gpu-worker.md` cho máy GPU thuê:
  - Yêu cầu: Linux, driver đủ cho bản torch, ≥ 12 GB VRAM.
  - Tailscale userspace (`tailscaled --tun=userspace-networking`); cài CLI worker, ghép mã, qualification.
  - Engine strict mới nghiệm thu trên SM86/SM120; GPU khác chạy không-strict hoặc phải qualify trước.

## 6. Việc chỉ chủ dự án làm (Codex ghi lệnh dán sẵn vào HANDOFF, không chờ)

| # | Việc | Codex làm gì khi chưa có |
| --- | --- | --- |
| O1 | Tạo repo GitHub `heteroes-minicloud` (public/private tùy bạn) | commit local, đưa lệnh `git remote add` + push |
| O2 | Tạo tài khoản Docker Hub + `docker login` trên máy 5070 Ti; ghi user vào file riêng | build sẵn, đưa lệnh `push-images.sh` |
| O3 | Tạo EC2 theo C7 + security group + key pair; ghi IP + đường dẫn khóa vào file riêng; đặt AWS Budget cảnh báo 20/50/80 USD | làm hết local, `deploy-ec2.sh` sẵn sàng |
| O4 | (tùy chọn) Tạo khóa Tailscale cho EC2 | demo EC2 không có worker GPU |
| O5 | Điền `team.json` (họ tên Khang, ngày sinh, GPA…), cung cấp `avatar.jpg`, PDF báo cáo | dùng dữ liệu "mẫu" đã đánh dấu |
| O6 | Quay video demo, sửa bản nháp báo cáo | có kịch bản sẵn |
| O7 | Quyết định deploy bản sửa của phần A/B lên lab thật (`local-lab.py`) | không deploy |
| O8 | (tùy chọn) Thuê GPU | có hướng dẫn sẵn |
| O9 | Sửa unit systemd đã cài nếu còn lỗi (ghi chú cũ trong HANDOFF) | không đụng |

## 7. Bàn giao và lệnh khởi động Codex

- Lời nhắn khởi động (chủ dự án dán vào Codex, chạy chế độ toàn quyền, thư mục `~/projects/heteroes`): xem khối
  "Lời nhắn khởi động" mà Claude đưa trong chat ngày 2026-10-31. Lời nhắn đó trỏ tới file này và kèm mật khẩu sudo.
- Kết thúc phần nào thì cập nhật `docs/HANDOFF.md` (tóm tắt tiếng Việt cho chủ dự án, trạng thái FINDINGS-A/B, biên bản
  nghiệm thu, các việc O1–O9 còn chờ kèm lệnh) và `PROGRESS.md` của repo 2.

## Kiểm tra cuối cùng (định nghĩa "xong")

1. FINDINGS-A: A-001…A-017, A-019, A-020 có trạng thái "đã sửa + test + commit". A-018 là thông tin. A-005/006/009 là commit tài liệu.
   FINDINGS-B: B-001…B-003 đã sửa, B-Q1/Q2 đã trả lời.
2. Biên bản nghiệm thu ở hash cuối, PASS trên 5070 Ti, 3060 WSL2, 3060 native. Check pytest có số passed/skipped.
   Evidence P-FROZEN chứng minh bit-identical.
3. Test backend xanh trên cả SQLite và Postgres. `check-all.sh` và `build-apps.sh --check` xanh. Bảng route khớp.
4. Repo 2: `check-minicloud.sh local` có mọi dòng của bảng C4 PASS (H1–H6 PASS, hoặc nêu lý do cụ thể nếu thiếu máy).
   Có ảnh chụp, có `out/BaoCao-Cuoi-Ky-Cloud.docx`.
5. Nếu O2/O3 đã có: image trên Docker Hub, `check-minicloud.sh ec2` PASS qua public IP.
6. `main` của repo 1 đã fast-forward và push. Lab thật không bị đụng (`local-lab.py status` trước/sau giống nhau).
