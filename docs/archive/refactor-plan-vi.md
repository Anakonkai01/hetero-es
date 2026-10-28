# Kế hoạch: gộp thành MỘT repo HeteroES và dọn dẹp code

## Bối cảnh
Bạn thấy dự án đang "phình to". Hiện có:
- 2 repo git: lõi `hetero-es` và sản phẩm `Hetero-ES-LLM`.
- 5 thư mục checkout, một bản snapshot review ngày 12/10 kèm file zip, thư mục `heteroes-test` (1,9 GB checkpoint từ 29/09), và một file `handoff.md` nằm lẻ.

Bên trong code còn:
- Chế độ điều khiển cũ (đã đóng băng theo D1) vẫn nằm trong code chính, và đa số bài kiểm tra vẫn chạy trên nó.
- Chế độ dữ liệu giả (mock) của web.
- Code cloud (EC2/R2/DuckDNS) dù cloud đã gác lại.
- Khoảng 24 script chỉ dùng một lần ở M1–M3.
- Các file bị chép tay giữa hai repo (`backend/monitoring`, `backend/study`).
- Nhiều đoạn kiểm tra lặp lại trong backend, hàm dài 300–500 dòng, dòng code dài tới 390 ký tự.
- Một chuỗi 7 file bàn giao nối nhau.

**Mục tiêu:**
- Còn một repo và một thư mục làm việc.
- Không còn thứ gì không dùng trong cây mã nguồn (mọi thứ vẫn còn trong lịch sử git).
- Code đang dùng dễ đọc hơn mà hành vi không đổi.
- Lab `lab.heteroes.site` vẫn chạy (chỉ tắt vài phút lúc chuyển).
- Mọi bài kiểm tra đều đạt.

Còn 32 ngày tới demo ngày 20/11. Ước tính việc dọn dẹp mất khoảng 5–7 ngày làm việc. Sau đó mới tới làm đẹp bộ cài (bản r11) và tập demo.

## Quyết định của bạn (19/10/2026)
- Giữ toàn bộ lịch sử commit của cả hai repo; mọi mã commit cũ vẫn tra được.
- Bố cục: lõi vào `runtime/`, phần sản phẩm giữ nguyên ở gốc.
- Thư mục cũ được **chuyển vào `~/projects/_old/`**, không xóa.
- Chỉ một mình bạn làm. Không push. Remote GitHub để bạn quyết sau.
- Bỏ hẳn mock web. Bỏ chế độ điều khiển cũ, nhưng **trước đó** chuyển test và lab mẫu sang chế độ agent. Xóa code cloud (vẫn lấy lại được từ nhánh `feat/m2-cloud-control`).
- Định dạng tự động toàn repo, **kể cả phần số học Recipe v1**. Chỉ đổi cách trình bày, kèm bằng chứng là cây cú pháp (AST) không đổi.

Các quy tắc cũ vẫn giữ:
- Viết test trước, sau đó kiểm tra đột biến (mutation check) trên bản sao.
- Commit theo nhóm logic, không có dòng Co-Authored-By, không push, không tag.
- Lab chỉ được thay đổi qua `scripts/local-lab.py`.
- GPU chỉ dùng khi bạn cho phép, kèm `--gpu` và `HETEROES_GPU_ACCEPTANCE=1`.

---

## Giai đoạn 0 — Lưới an toàn (trước mọi thay đổi)
1. Chạy và lưu kết quả gốc trên các thư mục cũ:
   - Test lõi: `CUDA_VISIBLE_DEVICES='' PYTHONPATH=src …/envs/heteroes-match/bin/python -m pytest -q` (lần gần nhất: 2.115 đạt, 100 bỏ qua).
   - `scripts/check-all.sh docs/evidence/2026-10-19-baseline/checks`.
2. Bản lưu cuối trước khi gộp, theo cách đã làm ở các phiên trước (`scripts/archive-local-session.py`):
   - `git bundle --all` của cả hai repo.
   - Bản chụp cơ sở dữ liệu của lab.
   - Bản mã hóa trên `/mnt/Archive-2tb`, có thử khôi phục.

## Giai đoạn 1 — Tạo repo gộp `~/projects/heteroes` và chuyển lab sang
1. Clone mới cả hai repo vào thư mục nháp. **Không viết lại lịch sử repo gốc.**
   - Bản runtime: trên nhánh `feat/local-first-lf1`, tạo một commit "Move the runtime into runtime/" bằng `git mv` toàn bộ.
   - Repo mới: nhánh `main` bắt đầu từ product `c560d6f`, rồi `git merge --allow-unrelated-histories` với nhánh runtime vừa chuyển.
   - Kết quả: mã commit gốc của cả hai repo được giữ nguyên (đều là tổ tiên của `main`).
2. Đưa các nhánh cũ vào dạng nhánh lưu `archive/runtime/<tên>` và `archive/product/<tên>`, không dùng tag theo quy tắc của bạn. Như vậy mọi mã commit được trích trong tài liệu và bằng chứng đều tra được.
3. Sửa đường dẫn. Tìm toàn repo các chuỗi `hetero-es-m3-runtime`, `Hetero-ES-LLM-m3`, `../Hetero-ES-LLM/.venv-backend`, `hetero-es-integration`, `TRACK_A`. Các file chính:
   - `scripts/build-apps.sh:16`
   - `scripts/refresh-worker-runtime.py`, `scripts/refresh-server-runtime.py`
   - `scripts/refresh-monitoring.py`, `scripts/check-public-replay.py`
   - `deploy/heteroes-lab.user.service`, `scripts/check-all.sh` (biến `PYTHON`)
   - `AGENTS.md`
   - Ngoài repo: `~/.config/heteroes-m2/acceptance-devices.json` (khóa `runtime`)
4. Môi trường:
   - Tạo venv backend mới `.venv-backend/` ở gốc repo (đã có trong gitignore), lấy danh sách gói từ venv cũ (`pip freeze`, 32 gói).
   - Runtime vẫn dùng conda `heteroes-match`.
   - `npm ci` ở gốc, build `frontend/dist`.
   - Chép các symlink trong `frontend/public/downloads` (`cp -P`; chúng trỏ sang ổ Archive).
5. Chuyển lab sang repo mới (báo trước cho bạn; lab phải rảnh):
   - Chạy `local-lab.py stop` từ thư mục cũ.
   - Cài unit systemd mới trỏ vào `~/projects/heteroes`, `systemctl --user daemon-reload`, rồi start.
   - Kiểm tra: `local-lab.py status`, health công khai trả 200, `scripts/verify-public-lab.py`, thiết bị `3060-thao` vẫn APPROVED.
   - Đường lui: giữ file unit cũ, nếu lỗi thì start lại từ thư mục cũ.
6. Khi lab đã ổn trên repo mới, chuyển vào `~/projects/_old/`:
   - `hetero-es`, `hetero-es-integration`, `hetero-es-m3-runtime`
   - `Hetero-ES-LLM`, `Hetero-ES-LLM-m3`
   - `heteroes-claude-review-20261012` cùng file `.zip` và `.sha256`
   - `handoff.md`, `heteroes-test`
7. Nơi làm việc: nhánh `refactor/cleanup`. Xong và mọi kiểm tra đạt thì fast-forward vào `main`.

## Giai đoạn 2 — Bỏ chế độ điều khiển cũ (D1), làm test trước
1. **Trước tiên:**
   - Sửa lab mẫu `scripts/serve-test-lab.py` (dòng 21 và 95 đang dùng runtime giả kiểu cũ `test_api.Runtime`) để chạy ở chế độ agent, với thiết bị và agent giả giống lab thật.
   - Chuyển 78 test backend đang dùng runtime giả kiểu cũ sang chế độ agent. Test nào chỉ kiểm hành vi của chế độ cũ thì xóa, ghi rõ lý do trong commit.
   - Kết quả: các bài kiểm tra web trong `check-all.sh` bắt đầu kiểm đúng các trang lab thật đang hiển thị (ví dụ LabDevices).
2. Sau đó mới xóa:
   - **Backend:**
     - `backend/runtime.py`; chuyển `RuntimeRejected` sang một module lỗi chung trước (đang được dùng ở `store.py:14`, `devices.py:16`).
     - `store._dispatch_legacy_once` (`store.py:244-275`).
     - Mọi nhánh `agent_mode`: 8 trong `app.py`, 5 trong `store.py`, 3 trong `lab.py`.
     - Đường mặc định cũ `~/.config/heteroes-integration` (`app.py:598`).
     - Route `/contributions*` và trang `LabContributions`.
     - Kiểu sao lưu M1: `backup.create_bundle/restore_bundle`, `/platform/backups*`, `restore-lab.py`, `check-lab-backup.py`.
     - Gói `httpx`, nếu chỉ còn `runtime.py` dùng.
   - **Script SSH/integration:** `start-integration.sh`, `stop-integration.sh`, `manage-integration.py`.
   - **Lõi:** `product/gateway.py` và `product/backup.py`, là phía máy chủ của chế độ cũ và chỉ gateway gọi tới. Các module khác chỉ xóa khi không còn ai import (dựa trên đồ thị import đã quét: agent → runner → coordinator/dispatch vẫn được giữ).
   - **Frontend:** các nhánh `!agentMode` (`RuntimePages.tsx`, `LabOperationsPage.tsx`, `LabDevices.tsx`, `StudyAssets.tsx`, `RuntimeExperiment.tsx`).

## Giai đoạn 3 — Bỏ mock, cloud, script dùng một lần và code chết
1. **Mock web:**
   - Xóa `frontend/src/mocks/`, các trang và thành phần Mock*, `lib/dataSource.ts` cùng 89 nhánh `IS_MOCK` (29 file), phần bật MSW trong `main.tsx`.
   - Xóa `static/mockServiceWorker.js`, gói `msw`, lệnh `test:mock` và `scripts/check-local-demo.mjs`.
   - Xóa `LOCAL_BACKEND_HANDOFF.md`. Thay `frontend/README.md` (đang là mẫu của Vite) bằng README thật.
2. **Route không ai gọi** (đã đối chiếu với web, app Worker, app Server và agent):
   - `GET /workspaces`, `GET /worker-registry`, `GET /platform/storage`
   - `PATCH /device/endpoints`, `GET /experiments/{id}/monitoring-events`
   - `/my-workers`, `/my-resource-submissions`
   - Các trường giả thời mock trong `/resources`, route bắt-tất-cả trả 501
   - Kèm theo các hàm frontend không dùng: `getWorkspaces`, `useRegistry`, `createPool`, `registerDemoWorker`, `completeDemoExperiment`.
   - **Kiểm thêm:** giải nén runtime của bản r10 đang chạy ngoài thực tế (máy 3060 của Thảo) vào thư mục nháp, và chắc chắn nó không gọi route nào bị xóa.
3. **Cloud:**
   - Xóa: `S3Backend` (`cloud_storage.py:19-96`), nhánh `storageFile`, phần đếm request R2, các file `requirements-cloud*`, gói `boto3`.
   - Xóa trong `deploy/`: `Caddyfile`, `heteroes.service`, `install-cpu-server.sh`, `config.example.json` và các file mẫu `r2`/`ec2`/`agent`.
   - Xóa script: `cloud-preflight`, `provision-m2-ec2`, `update-duckdns`, `build-m2-release`, `verify-release`, `prepare-m2`.
   - **Đổi tên phần lưu trữ local đang chạy cho đúng nghĩa:**
     - `cloud_storage.py` → `recovery_storage.py`; `CloudStorage` → `RecoveryStorage`
     - `cloud_metadata.py` → `metadata_backup.py`
     - `restore-m2-metadata.py` → `restore-metadata.py`
     - `cloud-recovery.py` → `recovery.py`, chỉ giữ các lệnh còn dùng
   - **Tên bảng SQLite trên lab giữ nguyên** (`cloud_objects`…), có ghi chú lý do, để không phải viết migration trên dữ liệu thật.
4. **Script một lần (M1–M3).** Xóa khỏi cây; chúng vẫn còn trong lịch sử git.
   - Gồm: `check-m3-*`, `review-*`, `check-worker-bootstrap/ui`, `check-native-windows`, `check-live-quick`, `check-two-gpu-integration`, `check-runtime-recovery`.
   - Gồm: `scripts/checks/frontend/*.sh` (9 file), `frontend/scripts/check-{real-integration,m2-browser,lab-operations}.mjs`.
   - Gồm hai script nguy hiểm: `start-m3-preview.py` (dùng chung cấu hình và cổng 8002 với lab thật) và `share-worker-build.py` (ghi vào thư mục tải xuống của lab).
   - Script nghiên cứu trong `runtime/scripts` và `runtime/artifacts/` **được giữ**, vì báo cáo dựa trên chúng. Sẽ thêm `runtime/scripts/README.md` ghi rõ script nào để vận hành, script nào để nghiên cứu.
5. **Phần còn lại:**
   - Chạy `vulture` (Python) và `knip` (TS) một lần để tìm code chết.
   - Mỗi kết quả phải grep xác nhận trước khi xóa. Ví dụ đã thấy: `WorkersPage.tsx`, `SchedulingPage.tsx` không nằm trong router; các import không dùng ở `devices.py:11-12`, `deployment.py:6`, `store.py:10`, `study_registry.py:4`.
   - `assert/` (zip và bản giải nén giống hệt nhau): giữ một file zip ở `docs/archive/`.
   - `notes/`: chuyển sang `docs/archive/notes/`.

## Giai đoạn 4 — Gộp phần trùng lặp
1. **Bản chép giữa hai repo.** `backend/monitoring/*` (5 file) và `backend/study/*` (3 file) đang giống từng byte với `runtime/src/heteroes/product/*` và `heteroes/study/*`.
   - Hướng chính: chỉ giữ một nguồn ở `runtime/`. Backend import trực tiếp, còn `refresh-server-runtime.py` đóng các file đó vào gói Lab Server. Sau đó xóa bản chép, `provenance.json` và `refresh-monitoring.py`.
   - Điều kiện: các module đó không kéo theo torch. Sẽ kiểm import trước. Nếu có kéo theo thì giữ cách chép, nhưng sinh ra lúc build và kiểm trong `check-all.sh`.
2. **Logic lặp trong backend.** Mỗi việc dưới đây gom về một hàm hoặc hằng duy nhất, viết test trước:
   - Kiểm tra chính sách sao lưu (3 nơi)
   - Điều kiện thiết bị cho Recipe v2 (2 nơi)
   - Đọc `dispatchHold` (7 nơi), cập nhật `disabledWorkers` (6 nơi), kiểm tra reservation/drain (5 nơi)
   - Kiểm tra người dùng active/admin (3 nơi)
   - Trạng thái lưu trữ (2 nơi), đọc `config.json` riêng (3 nơi)
   - Hằng model/revision, tập trạng thái run, lớp `Strict` (đang có 2 bản khác nhau)
3. **Hai app desktop.** Phần electron chung giữa `desktop/worker` và `desktop/server` (setup, service, log, download; hiện có cả thư mục `desktop/server/electron/shared/` sinh ra lúc build) chuyển về một module `desktop/shared/`.

## Giai đoạn 5 — Code dễ đọc (hành vi không đổi)
1. **Định dạng tự động.**
   - Công cụ: `ruff format` cho Python (độ dài dòng 120), `prettier` cho TS/JS/CSS/JSON (bỏ qua `docs/evidence`, fixture và file sinh ra).
   - Làm thành **một commit riêng**, ghi mã commit vào `.git-blame-ignore-revs`.
   - **Bằng chứng:** một script so cây cú pháp (AST) của mọi file Python trước và sau. Chúng phải bằng nhau, nhất là `noise/`, `es/`, `ledger/`, `generation_record.py`. Test số học (vector chuẩn) phải đạt y như trước.
   - Thêm `ruff check`, `ruff format --check`, `prettier --check` vào `check-all.sh`.
2. **Tách các chỗ phình to trong code đang chạy:**
   - `app.create_app` (một closure 531 dòng) và `lab.install_lab_routes` (354 dòng): tách thành `APIRouter` theo nhóm chức năng.
   - `devices.AgentRuntime`: tách tạo bảng và migration (gom mọi CREATE TABLE về `migrations.py`), lập lịch, hàng đợi lệnh và xử lý poll (`poll` dài 104 dòng thì chia thành các bước).
   - Thay việc chạm vào thành viên riêng (`runtime._enqueue`, `storage._requests`) bằng phương thức công khai.
   - Ngoại lệ đang bị nuốt im lặng thì ghi log. Bỏ `if True:` và các `import re` đặt trong hàm.
3. **Lõi:**
   - `ledger/ledger.py` (871 dòng) và `product/agent.py` chỉ tách khi thật sự dễ đọc hơn.
   - Phần số học không đổi logic.
4. **Frontend và app:**
   - Tách `RuntimeExperiment.tsx`, `WorkspacePage.tsx`, `LabOperationsPage.tsx`, `desktop/worker/src/main.tsx` thành các component và hook nhỏ.
   - Xóa các khóa dịch không dùng trong `packages/product-ui/src/translations.ts`. `scripts/check-i18n.mjs` sẽ báo lỗi khi có khóa thừa.
5. **Phát hiện bảo mật.** Ví dụ `/health` để lộ `privateLabUrl`, và đường dẫn `/mnt/sekai` bị viết cứng. Những điểm này **chỉ liệt kê để bạn quyết**, không sửa ngầm, vì sửa sẽ đổi hành vi.

## Giai đoạn 6 — Tài liệu và một điểm vào duy nhất
- **Gốc repo:**
  - `README.md`: dự án là gì, bố cục thư mục, cách chạy kiểm tra, cách lab chạy.
  - `AGENTS.md`: một bộ quy tắc chung, gộp từ hai bản cũ.
  - `CLAUDE.md`: chỉ trỏ sang `AGENTS.md`.
- **`docs/HANDOFF.md`** duy nhất thay cho chuỗi 7 file bàn giao. Các file sau chuyển vào `docs/archive/`:
  - Bàn giao cũ, tài liệu M1/M2/M3.
  - Tài liệu tự ghi là đã bị thay thế: `m3-session-handoff`, `local-first-claude-handoff`, `lab-roadmap`, `m2-implementation`…
- **Tài liệu của lõi.** Giữ MASTER, STATUS, CLAIMS_AUDIT và contract số học trong `runtime/`, vì báo cáo cần chúng. HANDOFF và TODO của lõi gộp vào `docs/`.
- Cập nhật `quickstart-vi.md` (đang ghi r5, thực tế là r10).
- **`scripts/check-all.sh` thành lệnh duy nhất kiểm tra mọi thứ:** test lõi (conda env), test backend, unit test web và app, kiểu, lint, định dạng, i18n, các bài kiểm tra trình duyệt và Electron.
- `docs/evidence/` giữ nguyên theo chính sách bằng chứng. Chỉ thêm README cho `2026-10-13-ui-checks`, thư mục duy nhất chưa có.

## Kiểm chứng
- **Sau mỗi giai đoạn:**
  - Chạy `scripts/check-all.sh docs/evidence/2026-10-<ngày>-<giai đoạn>/checks` và phải đạt hết.
  - Ghi số test trước và sau, giải thích từng test bị xóa.
  - Code mới (các helper gộp, lab mẫu chế độ agent) phải qua kiểm tra đột biến bằng `scripts/mutation-check.py`.
- **Lịch sử:** mọi commit trong `git rev-list --all` của hai repo cũ đều có trong repo mới.
- **Định dạng:** AST của mọi file Python không đổi. Test số học (vector chuẩn) đạt như trước. `tsc` và `vite build` đều đạt.
- **Lab:**
  - `local-lab.py status`, health công khai 200, `verify-public-lab.py`.
  - Đăng nhập và mở các trang trên lab.heteroes.site.
  - Thiết bị `3060-thao` vẫn hiện và vẫn APPROVED.
  - Bản r10 đang chạy ngoài thực tế không gọi route nào bị xóa.
- **Đóng gói:** `scripts/build-apps.sh` build được từ bố cục mới (bản Linux unpacked, chỉ để kiểm tra). **Không phát hành bộ cài mới trong đợt dọn dẹp**; bản r11 sẽ ra cùng phần làm đẹp bộ cài.
- **Cuối cùng, chỉ khi bạn cho phép:** một lượt chạy ngắn thật trên 5070 Ti qua lab, với `--gpu` và `HETEROES_GPU_ACCEPTANCE=1`.

## Rủi ro và cách giảm
- **Lab tắt vài phút lúc chuyển** (giai đoạn 1.5). Làm lúc lab rảnh và có đường lui.
- **Đổi hành vi backend ngoài ý muốn.** Viết test chế độ agent trước, chạy check-all sau mỗi nhóm commit, kiểm tra lab thật sau khi chuyển.
- **Bộ cài Lab Server đóng gói mọi `backend/*.py`.** Mọi thay đổi backend đều làm đổi gói, nhưng bản r10 đã phát hành không bị ảnh hưởng vì là bản đóng gói riêng.
- **Thư mục cũ trong `_old/`.** Venv cũ sẽ hỏng vì đường dẫn tuyệt đối, nên lab phải dùng venv mới trước khi chuyển thư mục.
