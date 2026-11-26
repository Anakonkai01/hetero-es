# HeteroES — current state

Checked 2026-11-26 on the project workstation. See the [documentation map](README.md) for guides, the
[review guide](REVIEW-GUIDE.md) for code ownership and the [evidence index](EVIDENCE-INDEX.md) for dated records.

## Phiên bản và trạng thái

| Phạm vi | Phiên bản | Kết quả kiểm tra |
| --- | --- | --- |
| Bản cuối kỳ | Nhánh `feat/final-2026-12` (chưa push), nghiệm thu trên `83480c6d` = cây nguồn `src-3fce794a…` | [37/37 cặp đạt](acceptance/STATUS-src-3fce794a.md) (26 tại 5070 Ti, 8 trên 3060 WSL2, 3 trên 3060 Windows); M3 và M5 còn đúng hai cổng mở như B-021. Hai lần trượt có biên nhận: native thiếu `nvdisasm` (thêm `nvidia-cuda-nvdisasm==13.2.78`), `strict-e2e` lần đầu 3060 khởi động chậm nên chỉ làm audit. [Checklist](acceptance/FINAL-2026-12-CHECKLIST.md). |
| Lab công khai | `https://lab.heteroes.site`, bản cài ở `~/.local/share/heteroes-lab/app` theo `872152cf`; kho phục hồi `/mnt/sekai/HETEROES-LAB-KHONG-XOA/lab-storage-20261125` | Chạy. Trang tải phát hành worker Linux `20261126-872152cf` (runtime `3f1adea02535`); bundle `20261126-83480c6d` đã build, chưa phát hành; bộ cài Windows vẫn là `20261204-8d339686` (thiếu `cuda-bindings`/NVRTC). |
| Máy GPU của lab | `5070ti-nhan` (coordinator + worker); `5070ti-nhut`, `3060-quang`, `3060-thao` là máy mượn | 26/11 trưa: Nhựt và Thảo lên runtime `3f1adea02535`; Quang tắt, chưa cập nhật. `1660s` không hỗ trợ bộ suy luận nghiêm ngặt (sm75). |
| `main` upstream | `38327051` trên GitHub, cùng cây nguồn với `3429d810` | B-021 đạt 37/37 cặp kiểm tra–môi trường. [STATUS.md](acceptance/STATUS.md) nay là cây nguồn cuối. |

## Kết quả của đợt cuối kỳ (24–26/11)

- Thí nghiệm qua lab nằm ở `runtime/notebooks/experiments/` (notebook tiếng Việt, [README](../runtime/notebooks/experiments/README.md)).
  E4 Countdown × Qwen2.5-1.5B trên 4 GPU: test 4 → 31/250 (p = 4,6·10⁻⁷), 151/151 audit khớp. Chủ dự án (26/11): không chạy
  thêm thí nghiệm học (E1, E2, E5); máy mượn dùng cho phép đo hệ thống.
- Trưa 26/11 với máy Thảo (3060 WSL2) và máy Nhựt (5070 Ti); máy Quang tắt.
  [Bằng chứng](https://github.com/Anakonkai01/hetero-es/blob/evidence-archive/docs/evidence/2026-11-26-borrowed-machines-system/README.md):
  - Llama-3.2-1B parity trên RTX 3060 khớp golden của 5070 Ti (PARITY OK).
  - Tốc độ cấu hình E4, điểm khôi phục 10 thế hệ: 1/2/3 GPU = 102,5/71,2/69,9 s mỗi thế hệ (trung vị); thêm 3060 gần như
    không nhanh hơn (vào việc trễ 28 s, 7,3 s/candidate).
  - Thử chịu lỗi trên lab (run `94d9b883`): kill -9, off, on + thêm lại máy Nhựt; run xong 16/16, audit 12/12. Tìm ra lỗi
    audit chờ hết hạn khi máy khác không hỏi việc → sửa ở `83480c6d`.
- Mã mới trên nhánh: `4efd1596` + `099f20da` coordinator tự dọn run đã xong khi điểm mới nhất READY trên kho lab
  (`heteroes-worker clean --dry-run`, `HETEROES_KEEP_FINISHED_RUN_DATA=1` để tắt); `83480c6d` đóng lượt audit sau 30 s
  khi không còn máy nào có thể audit. Bundle worker `20261126-83480c6d` đã build ở
  `/mnt/Archive-2tb/HETEROES-LAB-KHONG-XOA/builds/20261126-83480c6d/cli`, **chưa phát hành** (chủ dự án chạy
  `~/heteroes-experiments/borrowed-20261126/publish-worker-83480c6d.sh`, rồi `heteroes-worker update` trên từng máy;
  máy Thảo WSL phải cài tay như ghi ở mục Vận hành).
- Lỗ hổng đóng gói: profile Worker Windows thiếu `cuda-bindings`/NVRTC nên app Windows không chạy được `strict_b22_v1`;
  môi trường nghiệm thu native 26/11 = profile Windows + `cuda-bindings==13.4.3` + `nvidia-cuda-nvrtc==13.2.78`
  (`D:\heteroes-accept-native-20261126`, junction từ đường dẫn trong `acceptance/hosts.py`).
- Báo cáo, slide và video demo nằm ngoài repo, ở `~/projects/bao-cao/heteroes-cuoi-ky-2026-12`.

## Vận hành cần nhớ

- Sau khi máy 5070 Ti khởi động lại (26/11), lab trả lời bình thường nhưng một run mới nằm ở hàng chờ mà không được giao
  (hàng chờ không bị giữ, không có giữ chỗ GPU). `python3 -I ~/.local/share/heteroes-lab/app/scripts/local-lab.py restart --python ~/.local/share/heteroes-lab/venv-backend/bin/python`
  khi lab rảnh làm hàng chờ chạy lại. Nguyên nhân chưa rõ; `local-lab.py stop` rồi `boot` (04:02 26/11) không tái hiện được
  (run thử được giao trong vài giây). Lần kẹt xảy ra sau một lần khởi động máy thật và ngay sau `heteroes-worker update`.
- Triển khai lab: `git -C ~/.local/share/heteroes-lab/app pull --ff-only`, build web vào thư mục tạm rồi thay `frontend/dist`,
  khởi động lại bằng `local-lab.py` của chính bản cài (không dùng bản trong repo).
- Phát hành worker Linux: worktree ở commit cần phát hành → `scripts/refresh-worker-runtime.py --track-a runtime` →
  `scripts/build-linux-worker.py --build <tên> --out /mnt/Archive-2tb/HETEROES-LAB-KHONG-XOA/builds/<tên>/cli` → cập nhật
  `linuxWorker` trong `frontend/public/downloads/manifest.json` của bản cài lab và các symlink (bản cũ được giữ).
  `scripts/publish-local-installers.py` đòi build lại cả bộ cài Windows, nên lần 26/11 chỉ thay phần Linux.
- Coordinator không tự dọn dữ liệu của run đã kết thúc: một run 1,5B giữ khoảng 20 GB (trọng số, hai điểm khôi phục, bản
  xuất). Run đã xong được chuyển tay sang `/mnt/Archive-2tb/HETEROES-LAB-KHONG-XOA/coordinator-archive-20261125/`
  (26/11: `5f0c79f0`, `6131a0ad`, `d4214933`). Ổ hệ thống cần ≥ 25 GB trống trước một run 1,5B; nên làm tự dọn sau khi
  điểm cuối đã kiểm chứng trên kho lab.
- Máy Thảo (WSL2): bộ cài worker từ chối WSL. Cập nhật tay: tải `install-worker.sh`, bỏ dòng "WSL is not supported", chạy
  với `HETEROES_WORKER_HOME=~/.local/share/heteroes-c4-cpu HETEROES_SKIP_SETUP=1`, rồi `heteroes-worker selftest` (PATH và
  LD_LIBRARY_PATH có `/usr/lib/wsl/lib`) và `heteroes-worker restart`. Đừng chạy `heteroes-worker clean` ở đó: nghiệm thu
  3060-wsl dùng Python của runtime cũ `9a553d2dfae9`. Các tệp nghiệm thu nằm đúng đường dẫn của `acceptance/hosts.py`
  (thư viện kiểm thử ở `/tmp`, mất khi WSL khởi động lại: cài lại bằng pip `--target`).
- Môi trường `ai` có PEFT 0.19.1 (bản ghim 0.21.2): 4 kiểm thử `test_v3_qualification` chạy bằng môi trường này thất bại;
  không sửa môi trường `ai`.

## Technical scope

- The accepted B-021 source is `src-c9f8f9d8dc7966ca95b8c36104cffeaf2ccc030d595fc4ed71266f9c2bb92229`.
  [Acceptance reports](acceptance/README.md) bind receipts to the source identity.
- The lab form defaults new Recipe v3 runs to `strict_b22_v1`. D1 permits one worker to share its coordinator's GPU
  when two estimated weight sets fit the 90% VRAM budget. `strict_int8_lora_v1` is available through the standalone
  runner and SDK. Exact parity was measured on SM86 and SM120. The B-021 short32/chat128 receipts record
  10,107.1/9,967.3 token/s on the 5070 Ti and 3,104.3/2,919.5 on the 3060 WSL.
- The product database holds lab metadata. The coordinator owns each run's ledger and update records. Model, dataset,
  and recovery bytes and metadata backup payloads have separate storage owners. See
  [data ownership and recovery](design/lab-server-architecture.md#b-q2-where-data-and-backups-live).

## Commands

```bash
python3 scripts/accept.py list
python3 scripts/accept.py report
export ACCEPT_PYTHON="$HOME/miniforge3/envs/heteroes-match/bin/python"
CUDA_VISIBLE_DEVICES='' python3 scripts/accept.py run cpu package --keep
HETEROES_GPU_ACCEPTANCE=1 python3 scripts/accept.py run mutation gpu perf faults --keep
python3 -I "$HOME/.local/share/heteroes-lab/app/scripts/local-lab.py" status
```

For remote commands, see [the acceptance guide](acceptance/README.md). WSL and native Windows share a GPU and must run
serially. Check the workstation lab before any authorized GPU work.

## Việc còn mở (báo cáo cuối kỳ nộp 04/12/2026)

- Chủ dự án: phát hành worker `20261126-83480c6d` (`~/heteroes-experiments/borrowed-20261126/publish-worker-83480c6d.sh`), rồi
  `heteroes-worker update` trên từng máy (Thảo: cài tay như mục Vận hành) và chạy lại phép thử chịu lỗi để xác nhận bản
  sửa audit trên lab.
- Sửa bộ cài Worker Windows (thêm `cuda-bindings`, `nvidia-cuda-nvrtc`) khi chủ dự án đồng ý; build lại bộ cài cần nghiệm thu lại.
- Probe `strict-e2e` phụ thuộc thời điểm khởi động worker: nên cho thế hệ 0 chờ đủ hai worker.
- Chủ dự án duyệt báo cáo (71 trang; mục 5.8, 5.11–5.13, chương 6), slide (31) và hai video; push khi đồng ý.
- Sau khi nghiệm thu và báo cáo xong: bộ suy luận nghiêm ngặt tổng quát (ghi chú thiết kế ở mục 6.3 của báo cáo).
