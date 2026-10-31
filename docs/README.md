# Tài liệu HeteroES — đọc gì, ở đâu

Muốn nắm hệ thống nhanh: đọc theo thứ tự 1 → 2 → 3. Tài liệu kỹ thuật chi tiết của lõi số học nằm ở [../runtime/docs/](../runtime/docs/README.md).

## 1. Trạng thái và review (đọc trước)

| File | Là gì |
| --- | --- |
| [HANDOFF.md](HANDOFF.md) | Một trang: dự án đang ở đâu, việc còn mở, lệnh hay dùng. Cập nhật tại chỗ. |
| [REVIEW-GUIDE.md](REVIEW-GUIDE.md) | Hướng dẫn cho người review: thứ tự đọc, bản đồ module, bất biến không được phá. |
| [REVIEW-PLAN.md](REVIEW-PLAN.md) | Kế hoạch chia việc review giữa hai người; kết quả ghi trong [review/](review). |
| [RELEASE-NOTES-2026-10-28.md](RELEASE-NOTES-2026-10-28.md) | Ghi chú bản phát hành đã deploy. |
| [acceptance/](acceptance/README.md) | Biên bản nghiệm thu (gate M0–M6) và trạng thái mới nhất. |

## 2. Hướng dẫn dùng và vận hành — [guides/](guides)

| File | Là gì |
| --- | --- |
| [quickstart-vi.md](guides/quickstart-vi.md) | Bắt đầu nhanh (tiếng Việt). |
| [server-desktop-guide.md](guides/server-desktop-guide.md) | Ứng dụng Server (Electron). |
| [worker-desktop-guide.md](guides/worker-desktop-guide.md) | Ứng dụng Worker (Electron). |
| [local-lab-operations.md](guides/local-lab-operations.md) | Vận hành lab đang chạy trên máy này. |

## 3. Thiết kế và quyết định — [design/](design)

| File | Là gì |
| --- | --- |
| [operations-decisions-2026-10-23.md](design/operations-decisions-2026-10-23.md) | Quyết định vận hành (oomd, soak, UI chạy dài). |
| [resource-monitoring-design.md](design/resource-monitoring-design.md) | Thiết kế theo dõi tài nguyên. |
| [plan-sdk-lab-bridge.md](design/plan-sdk-lab-bridge.md) | Kế hoạch cầu nối SDK ↔ lab (chưa làm). |
| [strict-integer-projection-design.md](design/strict-integer-projection-design.md) | Thiết kế phép chiếu số nguyên của engine strict. |
| [STRICT-PERFORMANCE-VLLM.md](design/STRICT-PERFORMANCE-VLLM.md) | So sánh tốc độ engine strict với vLLM (mục tiêu 80% đã đóng, không đạt). |

## 4. Ghi chú còn lại ở gốc `docs/`

- [SECURITY-NOTES.md](SECURITY-NOTES.md): ghi chú bảo mật (backend và giao diện nhắc tới tên file này).
- [RUNTIME-TODO.md](RUNTIME-TODO.md): việc tồn đọng của runtime (code nhắc tới tên file này).
- [EVIDENCE-INDEX.md](EVIDENCE-INDEX.md): mục lục chứng cứ, sinh tự động từ nhánh `evidence-archive` bằng `scripts/build-evidence-index.py`. Đừng sửa tay.

Bản thân chứng cứ (hàng nghìn file) không nằm trên `main` mà ở nhánh `evidence-archive`.
