# Theo dõi tài liệu và công việc ứng dụng web HeteroES

- **Mục tiêu:** xác định phần đang làm, tài liệu liên quan và các điểm còn vướng.
- **Hướng dẫn:** [guide.md](guide.md).
- **Chức năng:** [web_service_functionality.md](../web_service_functionality.md).
- **Checklist tổng:** [web_service_todolist.md](../web_service_todolist.md).
- **Hiện tại:** đang làm rõ phạm vi phiên bản đầu; đã lưu bản thảo use case trong `uncheck/`, chưa chốt chức năng bắt buộc và chức năng làm sau.
- **Notes:** chưa đối chiếu nhiệm vụ với code; không sử dụng bảng này để kết luận chức năng chưa được triển khai.

## 1. Tài liệu hiện có

| Tài liệu | Vai trò | Trạng thái |
|---|---|---|
| [guide.md](guide.md) | Giải thích cách đọc và tổ chức tài liệu. | Đã duyệt. |
| [web_service_functionality.md](../web_service_functionality.md) | Chức năng Backend và Frontend. | Đã duyệt; có quyết định còn mở. |
| [web_service_todolist.md](../web_service_todolist.md) | Kế hoạch và checklist tổng. | Đã duyệt; chưa đối chiếu tiến độ code. |
| [workspace-authentication-authorization.md](../workspace-authentication-authorization.md) | Nội dung thảo luận phân quyền trước đây. | Tài liệu tham khảo; quyền chi tiết còn cần thống nhất. |
| [basic_system_use_cases.md](uncheck/basic_system_use_cases.md) | Luồng sử dụng và chức năng cơ bản đề xuất. | Đã duyệt để lưu bản thảo; phạm vi chức năng chưa chốt. |

## 2. Theo dõi từng phần

| Mục trong checklist tổng | Tài liệu mô tả và checklist chi tiết | Tiến độ triển khai | Công việc tiếp theo / điểm còn vướng |
|---|---|---|---|
| 1. Phạm vi và quyết định còn mở | [Bản thảo use case](uncheck/basic_system_use_cases.md) đã có; checklist chi tiết chưa tạo. | Chưa đối chiếu code. | Đang thống nhất chức năng bắt buộc, chức năng làm sau và bên quản lý hàng đợi. |
| 2. Phân quyền workspace | Chưa tạo; có tài liệu tham khảo ở mục 1. | Chưa đối chiếu code. | Chốt bảng quyền Owner, Partner, Viewer. |
| 3. Lưu trữ dữ liệu | Chưa tạo. | Chưa đối chiếu code. | Chốt quan hệ dữ liệu và experiment với lần chạy. |
| 4. Hợp đồng Coordinator | Chưa tạo. | Chưa đối chiếu code. | Xác nhận thao tác, dữ liệu và hành vi được hỗ trợ. |
| 5. Hợp đồng Frontend | Chưa tạo. | Chưa đối chiếu code. | Xác định API theo hoạt động người dùng. |
| 6. Backend web | Chưa tạo. | Chưa đối chiếu code. | Dựa vào thiết kế quyền, dữ liệu và API đã chốt. |
| 7. Giao tiếp Coordinator | Chưa tạo. | Chưa đối chiếu code. | Cần hợp đồng tối thiểu để xây phần giả lập. |
| 8. Frontend | Chưa tạo. | Chưa đối chiếu code. | Kiểm tra phần có sẵn trước khi thiết kế và bổ sung. |
| 9. Kiểm tra tích hợp | Chưa tạo. | Chưa đối chiếu code. | Xác định hoạt động và điều kiện cần kiểm tra. |
| 10. Chạy và bàn giao | Chưa tạo. | Chưa đối chiếu code. | Ghi cách chạy và giới hạn khi có chức năng cụ thể. |
| 11. Thứ tự thực hiện | Nằm trong checklist tổng. | Chưa đối chiếu code. | Làm theo từng hoạt động đã chọn. |
| 12. Tổ chức tài liệu | Hướng dẫn và bảng theo dõi đã tạo. | Đã tạo cấu trúc tài liệu; xem mục 3. | Tạo tài liệu chi tiết khi bắt đầu từng phần. |

## 3. Bằng chứng tổ chức tài liệu

- Đã tạo [guide.md](guide.md) và bảng theo dõi này.
- Đã tạo [checklist tổng](../web_service_todolist.md).
- Đã tạo thư mục `check/` và `uncheck/`.
- Đã lưu [bản thảo use case](uncheck/basic_system_use_cases.md) trong `uncheck/`; nội dung chưa được chốt.
- `check/` hiện chưa có tài liệu.
- Notes: Git không lưu thư mục trống; `check/` có thể chưa xuất hiện khi clone repository.
- **Notes:** các tài liệu tổng ở cấp `chat_notes/` và tài liệu điều hướng ở cấp `docs/`; `check/` và `uncheck/` dành cho tài liệu từng chủ đề.
