# Hướng dẫn đọc và tổ chức tài liệu ứng dụng web HeteroES

- **Mục đích:** giúp người đọc hiểu vị trí tài liệu, cách theo dõi công việc và ý nghĩa của từng trạng thái.
- **Đối tượng:** thành viên dự án và người mới tìm hiểu hệ thống.
- **Phạm vi:** tài liệu phân tích, thiết kế và checklist thực hiện ứng dụng web.
- **Trạng thái:** nội dung đã được người dùng duyệt.
- **Notes:** tài liệu đã được duyệt không đồng nghĩa chức năng đã được lập trình xong.

## 1. Nên đọc từ đâu?

1. Đọc [web_service_functionality.md](../web_service_functionality.md) để hiểu hệ thống cần có những chức năng gì.
2. Đọc [web_service_todolist.md](../web_service_todolist.md) để biết các nhóm công việc cần thực hiện.
3. Đọc [index.md](index.md) để biết hiện đang làm phần nào và còn vướng điều gì.
4. Mở tài liệu mô tả của phần cần tìm hiểu.
5. Mở checklist tương ứng để xem từng nhiệm vụ và bằng chứng hoàn thành.

- **Notes:** file chưa được tạo sẽ được ghi rõ trong bảng theo dõi; không coi là tài liệu đã có.

## 2. Bố cục thư mục

| Vị trí | Nội dung | Khi nào sử dụng? |
|---|---|---|
| `guide.md` | Hướng dẫn đọc và tổ chức tài liệu. | Khi mới tiếp cận hoặc cần hiểu quy ước. |
| `index.md` | Bảng theo dõi các phần, tiến độ và liên kết tài liệu. | Khi cần biết nhóm đang làm gì. |
| `check/` | Tài liệu đã được duyệt và thống nhất. | Khi cần tra cứu quyết định hiện hành. |
| `uncheck/` | Tài liệu đang soạn, thảo luận hoặc chờ duyệt. | Khi cần tiếp tục làm rõ nội dung. |

- Tên file dùng chữ thường, không thêm ngày ở đầu.
- Mỗi chủ đề được cập nhật trong tài liệu tương ứng.
- Không tạo nhiều bản trùng nội dung để thể hiện tiến độ.
- Notes: Git không lưu thư mục trống; `check/` có thể chưa xuất hiện khi clone repository cho đến khi có tài liệu bên trong.

## 3. Vì sao chia thành `check/` và `uncheck/`?

- Giúp người đọc phân biệt quyết định đã chốt với nội dung còn đang đề xuất.
- Tránh dùng một đề xuất chưa được duyệt làm yêu cầu chính thức.
- Giúp tìm nhanh những nội dung cần tiếp tục thảo luận.
- Cho phép thay đổi thiết kế mà vẫn xác định rõ trạng thái hiện tại.
- **Notes:** đây là cách phân loại trạng thái tài liệu, không phải phân loại code hoàn thành hay chưa.

## 4. Hai loại tài liệu cho mỗi phần

| Loại | Nội dung | Câu hỏi được trả lời |
|---|---|---|
| Tài liệu mô tả | Mục tiêu, phạm vi, quy tắc, dữ liệu và các quyết định. | Chúng ta cần làm gì và làm theo quy tắc nào? |
| Tài liệu checklist | Các nhiệm vụ cụ thể và điều kiện hoàn thành. | Cần thực hiện những bước nào, đã làm đến đâu? |

- **(Ví dụ minh họa):**
  - `workspace_access.md`: mô tả quyền trong workspace.
  - `workspace_access_todo.md`: checklist thiết kế, hiện thực và kiểm tra quyền.
- Chỉ tạo tài liệu chi tiết khi bắt đầu phần tương ứng.
- Không bắt buộc hai tài liệu được duyệt cùng lúc.
- Liên kết hai tài liệu để người đọc chuyển qua lại.

## 5. Phân biệt trạng thái tài liệu và trạng thái công việc

| Nhóm trạng thái | Giá trị | Ý nghĩa |
|---|---|---|
| Tài liệu | Đang soạn | Nội dung chưa đầy đủ. |
| Tài liệu | Chờ duyệt | Nội dung đã chuẩn bị, đang chờ thống nhất. |
| Tài liệu | Đã thống nhất | Nội dung đã được duyệt. |
| Công việc | Chưa bắt đầu | Chưa thực hiện nhiệm vụ. |
| Công việc | Đang làm | Đang thực hiện nhiệm vụ cụ thể. |
| Công việc | Bị chặn | Thiếu quyết định hoặc điều kiện cần thiết để tiếp tục. |
| Công việc | Hoàn thành | Đã đạt điều kiện và có bằng chứng. |

- **(Ví dụ minh họa):** bảng quyền đã thống nhất và nằm trong `check/`, nhưng việc lập trình kiểm tra quyền vẫn đang làm.
- **Notes:** `check/` không có nghĩa mọi ô trong checklist đã được đánh dấu hoàn thành.

## 6. Thông tin cần có trong mỗi tài liệu

- **Thuộc mục:** liên kết đến nhóm công việc trong checklist tổng.
- **Mục tiêu:** kết quả tài liệu hoặc công việc hướng đến.
- **Trạng thái tài liệu:** đang soạn, chờ duyệt hoặc đã thống nhất.
- **Trạng thái công việc:** ghi trong checklist tương ứng.
- **Tài liệu liên quan:** liên kết đến mô tả, checklist và nguồn tham khảo.
- **Cần thống nhất:** các câu hỏi chưa được quyết định.
- **Bằng chứng:** liên kết code, kết quả kiểm tra hoặc nội dung đã duyệt khi có.

## 7. Cách cập nhật tài liệu và tiến độ

1. Kiểm tra tài liệu hiện có trước khi tạo mới.
2. Soạn nội dung mới trong `uncheck/`.
3. Trình bày nội dung hoặc thay đổi để người dùng duyệt trước khi ghi file; ghi rõ đây là duyệt để lưu bản thảo hay chốt nội dung.
4. Chỉ chuyển tài liệu sang `check/` khi nội dung đã được chốt; nếu chỉ duyệt để lưu bản thảo hoặc còn quyết định chưa chốt, giữ trong `uncheck/` và ghi rõ trạng thái.
5. Cập nhật vị trí và liên kết trong `index.md` cùng các tài liệu liên quan.
6. Trong quá trình thực hiện, cập nhật checklist và bằng chứng.
7. Nếu cần sửa nội dung đã thống nhất, đưa tài liệu về `uncheck/` để duyệt lại.

- Bản đang sửa phải chỉ rõ phần thay đổi và quyết định đang cần xem xét.
- Thay đổi đề xuất chưa có hiệu lực cho đến khi được duyệt.
- Việc đồng ý lưu tài liệu không tự biến các đề xuất hoặc câu hỏi còn mở thành quyết định chính thức.
- **Notes:** cập nhật ô tiến độ và bằng chứng trong checklist không tự làm mất hiệu lực nội dung kế hoạch đã duyệt; sửa phạm vi hoặc quy tắc thì cần duyệt lại.

## 8. Nguyên tắc đánh dấu hoàn thành

- Dùng `[ ]` cho nhiệm vụ chưa xác nhận hoàn thành.
- Dùng `[x]` khi đạt điều kiện hoàn thành.
- Ghi bằng chứng phù hợp với loại nhiệm vụ.
  - Thảo luận: quyết định đã được duyệt.
  - Thiết kế: tài liệu đủ nội dung và đã thống nhất.
  - Lập trình: code đã hiện thực và kiểm tra phù hợp.
- Không đánh dấu hoàn thành chỉ vì đã tạo file hoặc viết code.
- Khi bị chặn, ghi nguyên nhân và điều kiện để tiếp tục.

## 9. Cách trình bày cho người mới đọc

- Viết ngắn gọn, mỗi ý diễn đạt một nội dung.
- Dùng bảng khi cần so sánh hoặc theo dõi.
- Giải thích thuật ngữ tiếng Anh bằng tiếng Việt ngay khi sử dụng.
- Ghi “(Đề xuất của trợ lý)” cho nội dung chưa được duyệt.
- Ghi “(Ví dụ minh họa)” cho tình huống ví dụ.
- Đặt câu hỏi chưa chốt trong mục “Cần thống nhất”.
- Dùng “Notes:” cho nhận xét bổ sung.
- Tuân thủ [quy ước tài liệu](../document_format.md).
