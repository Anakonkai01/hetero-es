# HeteroES — current state

Checked 2026-11-21 on the project workstation. See the [documentation map](README.md) for guides, the
[review guide](REVIEW-GUIDE.md) for code ownership and the [evidence index](EVIDENCE-INDEX.md) for dated records.

## Phiên bản và trạng thái

| Phạm vi | Phiên bản | Kết quả kiểm tra |
| --- | --- | --- |
| Mã nguồn có B-022 | Bản sửa `411a0a3a`, nhánh `fix/b022-final-point-projection` ở `8f5dc4f5` | Checkpoint định kỳ xác minh muộn không thay checkpoint cuối đã xác minh. Đã có hồi quy backend. [Nghiệm thu M0–M6](acceptance/STATUS-src-89176a3d.md) cho cây nguồn này chưa chạy đủ ma trận. |
| `main` upstream | `38327051` trên GitHub, cùng cây nguồn với `3429d810` | B-021 đạt 37/37 cặp kiểm tra–môi trường. [Biên bản nghiệm thu](acceptance/STATUS.md). |
| Lab công khai | Clone triển khai riêng tại `10457f9a`. Bộ cài công bố gần nhất là `lf1-20261014-r10` | Ngày 21/11, CPU server, public entry và named tunnel đều dừng. Unit lặp khởi động vì không tìm thấy ổ lưu trữ đã cấu hình. [Vận hành lab](guides/local-lab-operations.md). |

- Đã sửa các finding phần A và kiểm chứng P-FROZEN. Backend phần B có năm chế độ CPU, chạy SQLite ở chế độ gộp
  hoặc PostgreSQL ở chế độ tách service. OIDC và S3 là tùy chọn triển khai. Xem [kiến trúc backend](design/lab-server-architecture.md),
  [FINDINGS-A](review/FINDINGS-A.md) và [FINDINGS-B](review/FINDINGS-B.md).
- B-021 đạt 37/37 trên CPU, RTX 5070 Ti, RTX 3060 WSL và RTX 3060 Windows native. Bộ backend có MinIO đạt
  704 test SQLite và 733 test PostgreSQL. Các builder đã kiểm byte của app Linux, còn runtime Python riêng đã chạy kiểm
  HTTP thực trên cả Linux và Windows. [Biên bản B-021](https://github.com/Anakonkai01/hetero-es/blob/evidence-archive/docs/evidence/2026-11-03-b021-final-checkpoint-acceptance/README.md).
- Cây nguồn B-022 có hồi quy cho cả hai thứ tự xác minh checkpoint. Biên bản lúc sửa ghi 690 test SQLite và 716 test
  PostgreSQL, với bộ MinIO tùy chọn tắt. Kiểm tra này có phạm vi riêng với ma trận 37 cặp.

## Technical scope

- The accepted B-021 source is `src-c9f8f9d8dc7966ca95b8c36104cffeaf2ccc030d595fc4ed71266f9c2bb92229`.
  B-022 is `src-89176a3d955c8157f52d0a98facd7001f91f63fefa672a8df6ca43e2a2ce9c82`.
  [Acceptance reports](acceptance/README.md) bind receipts to the source identity.
- The lab form defaults new Recipe v3 runs to `strict_b22_v1`. A strict run needs a coordinator GPU distinct
  from its workers (D1). `strict_int8_lora_v1` is available through the standalone runner and SDK. Exact parity was
  measured on SM86 and SM120. The B-021 short32/chat128 receipts record 10,107.1/9,967.3 token/s on the 5070 Ti and
  3,104.3/2,919.5 on the 3060 WSL.
- On the accepted tree, M3.bookkeeping and M5.release remain open. M1.architectures and M3.full-disk are deferred.
  The standalone 600-generation soak measures its own runner. See the [acceptance report](acceptance/STATUS.md).
- The product database holds lab metadata. The coordinator owns each run's ledger and update records. Model, dataset,
  and recovery bytes and metadata backup payloads have separate storage owners. See
  [data ownership and recovery](design/lab-server-architecture.md#b-q2-where-data-and-backups-live).

## Commands

```bash
python3 scripts/accept.py list
python3 scripts/accept.py report
export ACCEPT_PYTHON="$HOME/miniforge3/envs/heteroes-match/bin/python"
CUDA_VISIBLE_DEVICES='' python3 scripts/accept.py run cpu
python3 -I "$HOME/.local/share/heteroes-lab/app/scripts/local-lab.py" status
```

For GPU and remote commands, see [the acceptance guide](acceptance/README.md). WSL and native Windows share a GPU and
must run serially. Check the workstation lab before any authorized GPU work.

## Việc còn mở

- Khôi phục điều kiện khởi động lab theo [hướng dẫn vận hành](guides/local-lab-operations.md). Unit đã dùng Python trong
  venv như template. Ổ lưu trữ với UUID đã cấu hình cần có mặt để lần thử tiếp theo khởi động được.
- Nghiệm thu B-022 trên ba môi trường trước khi đưa vào `main`. Việc triển khai lên lab công khai do chủ dự án quyết định riêng.
