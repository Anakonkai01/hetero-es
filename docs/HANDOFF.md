# HeteroES — current state

Checked 2026-11-24 on the project workstation. See the [documentation map](README.md) for guides, the
[review guide](REVIEW-GUIDE.md) for code ownership and the [evidence index](EVIDENCE-INDEX.md) for dated records.

## Phiên bản và trạng thái

| Phạm vi | Phiên bản | Kết quả kiểm tra |
| --- | --- | --- |
| Bản cuối kỳ đang nghiệm thu | `8d339686` trên `feat/final-2026-12` | [Cây nguồn `src-7787621f…`](acceptance/STATUS-src-7787621f.md) đạt 10/37 cặp CPU và đóng gói. |
| Nhánh tài liệu hiện tại | Cùng mã chạy B-022. README cấp module và notebook tham gia vào mã định danh của công cụ nghiệm thu. | [Trạng thái theo cây tài liệu hiện tại](acceptance/STATUS-src-af91b853.md). |
| Mã nguồn có B-022 | Bản sửa `411a0a3a`, nhánh `fix/b022-final-point-projection` ở `8f5dc4f5` | Checkpoint định kỳ xác minh muộn không thay checkpoint cuối đã xác minh. Đã có hồi quy backend. [Nghiệm thu M0–M6](acceptance/STATUS-src-89176a3d.md) cho cây nguồn này chưa chạy đủ ma trận. |
| `main` upstream | `38327051` trên GitHub, cùng cây nguồn với `3429d810` | B-021 đạt 37/37 cặp kiểm tra–môi trường. [Biên bản nghiệm thu](acceptance/STATUS.md). |
| Lab công khai | Clone triển khai riêng tại `10457f9a`. Bộ cài công bố gần nhất là `lf1-20261014-r10` | Dừng. Ổ Archive vẫn gắn đúng UUID nhưng thư mục kho `artifacts/lab-storage-20261012` đã bị xóa (khoảng 7/11, không còn trong thùng rác). Cơ sở dữ liệu vẫn ghi các object là READY, nên không được tạo lại thư mục rỗng: upload trùng SHA sẽ bị bỏ qua. Chủ dự án chọn cài lại lab sạch (24/11). [Vận hành lab](guides/local-lab-operations.md). |

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
  This documentation checkout has source identity `src-af91b85367c3e0dae4e5e975a4082b59d706b32a6cbfb9aebfe6e13fce726dab`.
  [Acceptance reports](acceptance/README.md) bind receipts to the source identity.
- The lab form defaults new Recipe v3 runs to `strict_b22_v1`. On the final branch, D1 permits one worker to share
  its coordinator's GPU when two estimated weight sets fit the 90% VRAM budget. The assignment retains the physical
  reservation when the worker leaves. `strict_int8_lora_v1` is available through the standalone runner and SDK. Exact parity was
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

## Việc còn mở (kế hoạch nộp báo cáo cuối kì 04/12/2026)

- Nhánh làm việc `feat/final-2026-12` (từ nhánh docs 21/11, có B-022): gỡ MiniCloud và course API, thêm
  `python -m heteroes.v3 derive` (nối tiếp run từ trọng số đã kiểm chứng, [hướng dẫn](../runtime/docs/v3-local-runs.md#continue-an-earlier-run))
  và bộ dữ liệu số học `runtime/scripts/build_arithmetic_dataset.py`.
- Commit `8d339686` hoàn thiện D1 và luồng **Chạy tiếp từ checkpoint** cho run Recipe v3 trên web. Điểm phục hồi
  phải là `READY` trong cùng workspace. Coordinator tải trọng số qua quyền của phân công mới và kiểm SHA trước
  khi mở thế hệ 0. Theo dõi các ca còn lại trong [checklist nghiệm thu](acceptance/FINAL-2026-12-CHECKLIST.md).
- Nghiệm thu cây nguồn cuối trên CPU, 5070 Ti, 3060 WSL và 3060 Windows trước khi đưa vào `main`.
- Cài lại lab sạch trên kho mới, rồi chủ dự án ghép lại worker (5070 Ti, 3060-thao).
- MiniCloud đã bị chủ dự án bỏ (24/11); repo GitHub `Anakonkai-AI-Group/heteroes-minicloud` được giữ nguyên.
