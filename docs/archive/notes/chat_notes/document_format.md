# Quy ước tài liệu trong chat_notes

- Mục đích: thống nhất cách trình bày và cập nhật tài liệu.
- Phạm vi: các file Markdown trong chat_notes/.
- Trạng thái: đã được người dùng duyệt.

## 1. Bố cục

- Dùng một tiêu đề chính để xác định chủ đề.
- Sau tiêu đề chính, trình bày thông tin tổng quan bằng danh sách ngắn.
- Chia nội dung thành các mục có tiêu đề rõ ràng.
- Chọn danh sách hoặc bảng theo cách giúp nội dung ngắn gọn, dễ đọc.
  - Dùng danh sách cho các ý độc lập hoặc giải thích có ý bổ sung.
  - Dùng bảng để so sánh, ánh xạ hoặc trình bày các mục có cùng thuộc tính.
- Mỗi bullet diễn đạt một ý ngắn gọn.
  - Giải thích hoặc điều kiện bổ sung đặt ở bullet con.
- Chỉ dùng sơ đồ hoặc code khi giúp làm rõ nội dung và đã được duyệt.
- Ưu tiên sự rõ ràng; tránh lặp lại cùng nội dung ở bảng và danh sách.

## 2. Phân biệt nội dung

- Nội dung đã thống nhất được ghi trực tiếp.
- Nội dung lấy từ tài liệu được ghi nguồn khi cần.
- Đề xuất chưa được duyệt ghi “(Đề xuất của trợ lý)”.
- Ví dụ minh họa ghi “(Ví dụ minh họa)”.
- Câu hỏi chưa chốt đặt trong mục “Cần thống nhất”.
- Nhận xét ngoài nội dung chính bắt đầu bằng “Notes:”.
  - Notes: không coi nhận xét hoặc đề xuất là quyết định chính thức.

## 3. Quy trình ghi file

- Trình bày đường dẫn và toàn bộ nội dung dự kiến trước khi tạo file.
- Khi sửa file, trình bày rõ phần sẽ thay đổi.
- Khi xóa file, trình bày đường dẫn và lý do.
- Chờ người dùng đồng ý trước khi thực hiện.
- Nếu nội dung thay đổi sau khi duyệt, trình bày lại phần thay đổi.
- Cập nhật một file thống nhất cho cùng chủ đề.
  - Không tự tạo thêm bản trùng hoặc bản có tên ngày/version.
- Sau khi ghi, kiểm tra nội dung và báo đường dẫn file.

## 4. Mẫu trình bày

- Role đã thống nhất: Owner, Partner, Viewer.
- Membership liên kết user với workspace.
  - Role được gán tại membership.
- (Đề xuất của trợ lý) Mỗi membership có một role.
- (Ví dụ minh họa) Khang là Owner ở Lab A và Viewer ở Lab B.
- Notes: role ở workspace khác không tạo quyền tại workspace hiện tại.

## 5. Phê duyệt tài liệu

- Quy ước này đã được người dùng duyệt và áp dụng cho các tài liệu trong `notes/chat_notes/`.
- Việc sửa tài liệu đã có phải được duyệt riêng.

## 6. Ngôn ngữ và thuật ngữ

- Viết để người chưa có kiến thức chuyên môn vẫn hiểu.
- Ưu tiên từ tiếng Việt quen thuộc và câu ngắn.
- Khi dùng thuật ngữ tiếng Anh, giải thích ngay trong ngoặc.
  - (Ví dụ minh họa) `LEASED (đã giao việc có thời hạn, chưa ghi nhận bắt đầu thực thi)`.
  - (Ví dụ minh họa) `Component (một phần giao diện)`.
- Giải thích thuật ngữ khi xuất hiện lần đầu trong mỗi mục có thể đọc độc lập.
- Không giải thích một thuật ngữ bằng các thuật ngữ khó khác chưa được giải thích.
- Dùng ví dụ cụ thể nếu định nghĩa ngắn chưa đủ rõ.
- Giữ nguyên tên file, tên hàm hoặc mã trạng thái khi cần đối chiếu code.
  - Bổ sung ý nghĩa tiếng Việt bên cạnh.
