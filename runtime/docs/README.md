# Tài liệu runtime (lõi số học và engine)

Đọc [numerical-contract.md](numerical-contract.md) trước: nó là "hợp đồng" nói chính xác mọi máy phải tính gì để cùng một candidate ra cùng một kết quả từng bit. Các ADR giải thích vì sao chọn như vậy. Tài liệu mức dự án nằm ở [../../docs/README.md](../../docs/README.md).

## Hợp đồng và cách chạy

| File | Là gì |
| --- | --- |
| [numerical-contract.md](numerical-contract.md) | Hợp đồng số học: nhiễu, perturb, restore, cập nhật ES, bản ghi thế hệ. Các mục §15–17 mô tả lựa chọn đời Recipe v1 (xem ADR-011/012/013 cho bản hiện hành). |
| [v3-local-runs.md](v3-local-runs.md) | Chạy Recipe v3 cục bộ bằng CLI/SDK. |
| [audit-state-v1.md](audit-state-v1.md) | Trạng thái kiểm toán khi chạy và điều kiện nhận bản cập nhật (M2). |
| [cpu-coordinator.md](cpu-coordinator.md) | Máy không GPU làm coordinator. |

## Quyết định kiến trúc — [adr/](adr)

| Nhóm | ADR |
| --- | --- |
| Nhiễu và sổ cái (đóng băng) | 001 nhiễu CPU PCG64 · 002 candidate/attempt/lease · 011 nhiễu số nguyên v2 |
| Triển khai và vòng đời | 003 worker từ xa · 004 local-first · 005 quyền trạng thái · 006 mạng/lưu trữ offline · 007 danh tính/phiên bản/khôi phục · 009 lập lịch |
| Recipe và đánh giá | 008 Recipe v3 · 010 chunk đánh giá theo thiết bị |
| Engine strict (cùng token trên mọi GPU) | 012 một model strict · 013 decoder B22 · 014 int8 + LoRA |

## Engine strict — [strict/](strict)

Đặc tả (đọc theo thứ tự này):

1. [strict-reference-v1.md](strict/strict-reference-v1.md): số học tham chiếu.
2. [integer-projection-v1.md](strict/integer-projection-v1.md): phép chiếu số nguyên B22.
3. [strict-decoder-v1.md](strict/strict-decoder-v1.md): decoder.
4. [frozen-int8-artifact-v1.md](strict/frozen-int8-artifact-v1.md): base int8 đóng băng + LoRA (thử nghiệm, chỉ SDK/standalone).

Ghi chú cách thực thi (không đổi số học, chỉ đổi cách chạy): [b22-streamed-projection](strict/b22-streamed-projection.md), [b22-paired-weight-reads](strict/b22-paired-weight-reads.md), [b22-weight-prefetch](strict/b22-weight-prefetch.md), [attention-tree-execution](strict/attention-tree-execution.md), [bounded-lm-head](strict/bounded-lm-head.md), [strict-lora-output-execution](strict/strict-lora-output-execution.md).
