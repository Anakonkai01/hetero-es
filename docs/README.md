# Tài liệu HeteroES — đọc gì, ở đâu

Xem [trạng thái và phiên bản](HANDOFF.md) trước khi làm việc với mã nguồn hoặc lab. Đặc tả lõi số học nằm ở [tài liệu runtime](../runtime/docs/README.md).

## 1. Trạng thái và review (đọc trước)

| File | Là gì |
| --- | --- |
| [HANDOFF.md](HANDOFF.md) | Nhánh mã nguồn, biên bản nghiệm thu theo phiên bản, tình trạng lab và việc còn mở. |
| [REVIEW-GUIDE.md](REVIEW-GUIDE.md) | Hướng dẫn cho người review: thứ tự đọc, bản đồ module, bất biến không được phá. |
| [REVIEW-PLAN.md](REVIEW-PLAN.md) | Kế hoạch review tháng 10. Kết quả nằm trong [review/](review). |
| [RELEASE-NOTES-2026-10-28.md](RELEASE-NOTES-2026-10-28.md) | Ghi chú bản phát hành đã deploy. |
| [acceptance/](acceptance/README.md) | Biên bản M0–M6 cho nguồn B-021 và báo cáo riêng của B-022. |

## 2. Hướng dẫn dùng và vận hành — [guides/](guides)

| File | Là gì |
| --- | --- |
| [quickstart-vi.md](guides/quickstart-vi.md) | Dùng bộ cài đã công bố gần nhất, dòng r10. |
| [server-desktop-guide.md](guides/server-desktop-guide.md) | Ứng dụng Server (Electron). |
| [worker-desktop-guide.md](guides/worker-desktop-guide.md) | Ứng dụng Worker (Electron). |
| [local-lab-operations.md](guides/local-lab-operations.md) | Kiểm tra và vận hành bản triển khai riêng của workstation. |
| [frontend/README.md](../frontend/README.md) | Chạy web UI với backend phát triển hoặc lab thử nghiệm CPU. |
| [runtime/README.md](../runtime/README.md) | Điểm vào CLI, SDK, notebook và lệnh kiểm tra runtime. |
| [runtime/scripts/README.md](../runtime/scripts/README.md) | Các script chạy worker, xử lý dữ liệu, kiểm tra và phục hồi. |

## 3. Thiết kế và quyết định — [design/](design)

| File | Là gì |
| --- | --- |
| [lab-server-architecture.md](design/lab-server-architecture.md) | Năm chế độ backend, các lớp mã nguồn và nơi lưu dữ liệu. |
| [container-configuration.md](design/container-configuration.md) | Các chế độ triển khai và cấu hình từ môi trường. |
| [oidc-authentication.md](design/oidc-authentication.md) | Đăng nhập local và OIDC. |
| [s3-storage.md](design/s3-storage.md) | Lưu object bằng S3/MinIO và luồng truyền riêng. |
| [postgres-metadata-backup.md](design/postgres-metadata-backup.md) | Sao lưu và khôi phục metadata PostgreSQL. |
| [observability.md](design/observability.md) | Liveness, readiness, metrics và log của backend. |
| [operations-decisions-2026-10-23.md](design/operations-decisions-2026-10-23.md) | Quyết định vận hành (oomd, soak, UI chạy dài). |
| [resource-monitoring-design.md](design/resource-monitoring-design.md) | Thiết kế theo dõi tài nguyên. |
| [plan-sdk-lab-bridge.md](design/plan-sdk-lab-bridge.md) | Cách SDK gửi run vào lab và dùng notebook nghiên cứu. |
| [strict-integer-projection-design.md](design/strict-integer-projection-design.md) | Thiết kế phép chiếu số nguyên của engine strict. |
| [STRICT-PERFORMANCE-VLLM.md](design/STRICT-PERFORMANCE-VLLM.md) | So sánh tốc độ engine strict với vLLM (mục tiêu 80% đã đóng, không đạt). |

## 4. Ghi chú còn lại ở gốc `docs/`

- [SECURITY-NOTES.md](SECURITY-NOTES.md): ghi chú bảo mật (backend và giao diện nhắc tới tên file này).
- [RUNTIME-TODO.md](RUNTIME-TODO.md) lưu backlog nghiên cứu đầu tháng 10. Việc đang mở được ghi trong [HANDOFF.md](HANDOFF.md).
- [EVIDENCE-INDEX.md](EVIDENCE-INDEX.md): mục lục chứng cứ, sinh tự động từ nhánh `evidence-archive` bằng `scripts/build-evidence-index.py`. Đừng sửa tay.

Bản thân chứng cứ (hàng nghìn file) không nằm trên `main` mà ở nhánh `evidence-archive`.
