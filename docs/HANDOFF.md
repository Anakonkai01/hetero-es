# HeteroES — current state

Checked 2026-11-26 on the project workstation. See the [documentation map](README.md) for guides, the
[review guide](REVIEW-GUIDE.md) for code ownership and the [evidence index](EVIDENCE-INDEX.md) for dated records.

## Phiên bản và trạng thái

| Phạm vi | Phiên bản | Kết quả kiểm tra |
| --- | --- | --- |
| Bản cuối kỳ | Nhánh `feat/final-2026-12` (chưa push), nghiệm thu trên `40c644af` = cây nguồn `src-95182970…` | [23/26 cặp tại máy 5070 Ti đạt](acceptance/STATUS-src-95182970.md) (CPU, đóng gói, 12 nhóm đột biến, GPU, hiệu năng). 3 cặp `strict-e2e*` cần máy 3060 của Thảo làm máy thứ hai (máy tắt), 11 cặp RTX 3060 chưa chạy lại. [Checklist](acceptance/FINAL-2026-12-CHECKLIST.md). |
| Lab công khai | `https://lab.heteroes.site`, bản cài ở `~/.local/share/heteroes-lab/app` theo `872152cf`; kho phục hồi `/mnt/sekai/HETEROES-LAB-KHONG-XOA/lab-storage-20261125` | Chạy. Trang tải phát hành worker Linux `20261126-872152cf` (runtime `3f1adea02535`); bộ cài Windows vẫn là `20261204-8d339686`. |
| Máy GPU của lab | `5070ti-nhan` (coordinator + worker, runtime mới); `5070ti-nhut`, `3060-quang`, `3060-thao` là máy mượn | Ba máy mượn tắt từ tối 25/11; khi bật lại cần `heteroes-worker update` để lên runtime mới. `1660s` không hỗ trợ bộ suy luận nghiêm ngặt (sm75). |
| `main` upstream | `38327051` trên GitHub, cùng cây nguồn với `3429d810` | B-021 đạt 37/37 cặp kiểm tra–môi trường. [Biên bản nghiệm thu](acceptance/STATUS.md). |

## Kết quả của đợt cuối kỳ (24–26/11)

- Thí nghiệm qua lab nằm ở `runtime/notebooks/experiments/` (notebook tiếng Việt, [README](../runtime/notebooks/experiments/README.md)).
  E4 Countdown × Qwen2.5-1.5B trên 4 GPU: test 4 → 31/250 (p = 4,6·10⁻⁷), 151/151 audit khớp. E1/E3 (GSM8K 512 token),
  E5 (Countdown 0,5B qua lab) và E2 (GSM8K × Llama-3.2-1B) chờ đủ GPU.
- Llama-3.2-1B (RoPE `llama3`) chạy với `strict_b22_v1` trên RTX 5070 Ti; golden parity
  `acceptance/golden/strict-b22-llama32.json` ghi trên 5070 Ti. Còn phải chạy trên RTX 3060:
  `HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=runtime/src:runtime/scripts python acceptance/probes/strict_parity.py --gpu --model llama32 --models <dir có llama32/> --out <file mới>`
  (thư mục mô hình: bản sao của `unsloth/Llama-3.2-1B-Instruct@5a8abab4…`). Không thuộc ma trận 37 cặp.
- Điểm khôi phục mặc định 10 thế hệ một lần. Đo trên một 5070 Ti (cấu hình E4): bước ghi điểm khôi phục 7,8 → 3,2 s
  mỗi thế hệ (trung vị); tổng một thế hệ chưa khác biệt rõ. Số đo 2/4 GPU chưa có.
  [Bằng chứng 26/11](https://github.com/Anakonkai01/hetero-es/blob/evidence-archive/docs/evidence/2026-11-26-llama32-parity-and-backup-interval/README.md).
- Báo cáo, slide và video demo nằm ngoài repo, ở `~/projects/bao-cao/heteroes-cuoi-ky-2026-12`.

## Vận hành cần nhớ

- Sau khi máy 5070 Ti khởi động lại (26/11), lab trả lời bình thường nhưng một run mới nằm ở hàng chờ mà không được giao
  (hàng chờ không bị giữ, không có giữ chỗ GPU). `python3 -I ~/.local/share/heteroes-lab/app/scripts/local-lab.py restart --python ~/.local/share/heteroes-lab/venv-backend/bin/python`
  khi lab rảnh làm hàng chờ chạy lại. Nguyên nhân chưa rõ.
- Triển khai lab: `git -C ~/.local/share/heteroes-lab/app pull --ff-only`, build web vào thư mục tạm rồi thay `frontend/dist`,
  khởi động lại bằng `local-lab.py` của chính bản cài (không dùng bản trong repo).
- Phát hành worker Linux: worktree ở commit cần phát hành → `scripts/refresh-worker-runtime.py --track-a runtime` →
  `scripts/build-linux-worker.py --build <tên> --out /mnt/Archive-2tb/HETEROES-LAB-KHONG-XOA/builds/<tên>/cli` → cập nhật
  `linuxWorker` trong `frontend/public/downloads/manifest.json` của bản cài lab và các symlink (bản cũ được giữ).
  `scripts/publish-local-installers.py` đòi build lại cả bộ cài Windows, nên lần 26/11 chỉ thay phần Linux.
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

- Khi các máy mượn bật lại: `heteroes-worker update` trên từng máy; chạy probe parity Llama trên RTX 3060; nghiệm thu
  `faults` tại máy này (`HETEROES_GPU_ACCEPTANCE=1 python3 scripts/accept.py run faults --keep`, cần máy Thảo) và
  3060 WSL/native (`scripts/accept.py remote 3060-wsl gpu perf`, `remote 3060-native gpu`) trên cây nguồn cuối; đo tốc độ 2/4 GPU với điểm khôi phục 10 thế hệ; E5 và E2 trên nhiều GPU.
- Chủ dự án duyệt báo cáo (mục 5.11–5.13 mới), slide và video; push nhánh khi chủ dự án đồng ý.
- Sau khi nghiệm thu và báo cáo xong: bộ suy luận nghiêm ngặt tổng quát (ghi chú thiết kế ở mục 6.3 của báo cáo).
