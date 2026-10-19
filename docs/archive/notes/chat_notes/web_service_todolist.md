# Danh sách công việc xây dựng ứng dụng web HeteroES

- **Mục tiêu:** chuyển các chức năng Backend và Frontend thành công việc có thể thực hiện và kiểm tra.
- **Nguồn:** [web_service_functionality.md](web_service_functionality.md).
- **Phạm vi:** ứng dụng web nhiều người dùng, kết nối Coordinator Service — dịch vụ điều phối thực thi ES.
- **Trạng thái:** kế hoạch đã được người dùng duyệt; chưa đối chiếu từng nhiệm vụ với code hiện tại.
- **Quy ước:** `[ ]` chưa xác nhận hoàn thành; `[x]` đã hoàn thành và có bằng chứng kiểm tra.
- **Hướng dẫn:** [docs/guide.md](docs/guide.md).
- **Theo dõi tổng:** [docs/index.md](docs/index.md).
- **Notes:** kiểm tra và tận dụng phần đã có trước khi xây mới; danh sách này không yêu cầu viết lại toàn bộ dự án.

## 1. Thống nhất phạm vi và các quyết định còn mở

- **Tài liệu đang thảo luận:** [basic_system_use_cases.md](docs/uncheck/basic_system_use_cases.md).
- **Trạng thái:** đã lưu bản thảo; chưa chốt chức năng bắt buộc hoặc chức năng làm sau.

- [ ] Xác định các chức năng bắt buộc của phiên bản đầu.
- [ ] Xác định các chức năng có thể làm sau.
- [ ] Chốt quyền của Owner, Partner và Viewer trong workspace — không gian làm việc.
- [ ] Chốt một người dùng có thể thuộc nhiều workspace hay không.
- [ ] Chốt số vai trò được gán cho mỗi membership — quan hệ thành viên.
- [ ] Chốt phạm vi tài nguyên GPU mà từng workspace được sử dụng.
- [ ] Chốt quan hệ giữa experiment — thí nghiệm ES — và từng lần chạy.
- [ ] Chốt thời điểm được chỉnh sửa cấu hình experiment.
- [ ] Chốt thành phần quản lý hàng đợi experiment.
- [ ] Xác định cách cung cấp tài khoản ban đầu, không mở rộng sang quản trị tài khoản toàn hệ thống nếu chưa cần.

- **Điều kiện hoàn thành:**
  - Các quyết định đã chốt được ghi rõ.
  - Mục chưa chốt có người phụ trách làm rõ.
  - Công việc phụ thuộc vào quyết định chưa chốt được đánh dấu.

## 2. Thiết kế phân quyền trong workspace

- [ ] Liệt kê các đối tượng cần kiểm tra quyền.
  - Workspace, thành viên, tài nguyên GPU, experiment, nhật ký và tệp kết quả.
- [ ] Lập bảng quyền theo từng hành động.
  - Xem, tạo, sửa, gửi chạy, yêu cầu hủy và tải kết quả.
- [ ] Phân biệt quyền với experiment của mình và experiment của người khác.
- [ ] Xác định cách xử lý khi người dùng không còn là thành viên.
- [ ] Xác định cách xử lý khi vai trò người dùng thay đổi.
- [ ] Chốt quy tắc thay đổi Owner nếu chức năng này được hỗ trợ.
- [ ] Xác định thông tin quyền backend cung cấp cho frontend.
- [ ] Chốt cách phản hồi khi chưa đăng nhập hoặc không đủ quyền.

- **Điều kiện hoàn thành:**
  - Mỗi hành động có quy tắc quyền rõ ràng.
  - Vai trò ở workspace này không tạo quyền tại workspace khác.
  - Quyền được kiểm tra ở backend, kể cả khi gọi API trực tiếp.

## 3. Thiết kế lưu trữ dữ liệu ứng dụng

- [ ] Chọn cơ sở dữ liệu phù hợp với quy mô triển khai.
- [ ] Thiết kế dữ liệu người dùng cần thiết cho ứng dụng.
- [ ] Thiết kế dữ liệu workspace và cấu hình.
- [ ] Thiết kế dữ liệu membership và vai trò.
- [ ] Thiết kế liên kết workspace với tài nguyên GPU.
- [ ] Thiết kế thông tin experiment và người sở hữu.
- [ ] Thiết kế liên kết experiment với mã lần chạy bên Coordinator.
- [ ] Thiết kế nhật ký thao tác người dùng.
- [ ] Thiết kế thông tin tra cứu kết quả và tệp đầu ra.
- [ ] Xác định dữ liệu thực thi nào cần lưu bản sao.
  - Ghi nguồn và thời điểm cập nhật của bản sao.
- [ ] Xác định quy tắc duy nhất và quan hệ giữa các dữ liệu.
  - **(Ví dụ minh họa):** tránh tạo hai membership cho cùng người dùng và workspace.
- [ ] Xác định thời gian lưu dữ liệu và nhật ký.

- **Điều kiện hoàn thành:**
  - Phân biệt được dữ liệu hiện tại với lịch sử thay đổi.
  - Phân biệt được dữ liệu ứng dụng sở hữu với dữ liệu Coordinator sở hữu.

## 4. Thống nhất API Contract giữa Backend web và Coordinator

- **API Contract:** thỏa thuận về thao tác, dữ liệu gửi nhận, lỗi và hành vi.
- **Notes:** nhóm công việc này có thể trao đổi song song với việc thiết kế phân quyền và lưu trữ.

### 4.1. Xác định khả năng dịch vụ

- [ ] Liệt kê các thao tác Coordinator hiện hỗ trợ.
- [ ] Xác định cách lấy danh sách Worker và khả năng thực thi.
- [ ] Xác định cách gửi cấu hình chạy experiment.
- [ ] Xác định cách lấy trạng thái và tiến độ.
- [ ] Xác định cách lấy sự kiện và nhật ký thực thi.
- [ ] Xác định cách yêu cầu hủy, nếu được hỗ trợ.
- [ ] Xác định cách lấy kết quả và danh sách tệp đầu ra.
- [ ] Đánh dấu chức năng chưa được Coordinator hỗ trợ.

### 4.2. Thống nhất dữ liệu và hành vi

- [ ] Chốt tên trường, kiểu dữ liệu và trường bắt buộc.
- [ ] Chốt ý nghĩa và phạm vi của các mã định danh.
- [ ] Chốt định dạng thời gian và đơn vị đo.
- [ ] Chốt các trạng thái và ý nghĩa từng trạng thái.
- [ ] Chốt cấu hình được phép gửi và lỗi cấu hình.
- [ ] Chốt thời điểm cấu hình được cố định cho lần chạy.
- [ ] Phân biệt “đã tiếp nhận yêu cầu” với “đã thực hiện xong”.
- [ ] Chốt cách xác định bên gọi có quyền sử dụng dịch vụ.
- [ ] Chốt thời gian chờ và cách xử lý mất kết nối.
- [ ] Chốt cách xử lý yêu cầu gửi lặp để tránh tạo trùng lần chạy.
- [ ] Chốt cách cập nhật trạng thái.
  - Hỏi định kỳ hoặc nhận thông báo từ dịch vụ.
- [ ] Chuẩn bị ví dụ phản hồi thành công, lỗi và dữ liệu trống.

- **Điều kiện hoàn thành:**
  - Có đủ thông tin để xây phần giả lập Coordinator.
  - Không tự suy đoán trạng thái hoặc chức năng chưa được xác nhận.

## 5. Thống nhất API Contract giữa Frontend và Backend web

- [ ] Liệt kê API cần thiết theo từng hoạt động người dùng.
- [ ] Chốt dữ liệu đăng nhập và phiên sử dụng.
- [ ] Chốt dữ liệu workspace, membership và quyền.
- [ ] Chốt dữ liệu tài nguyên GPU và Worker.
- [ ] Chốt dữ liệu danh sách và chi tiết experiment.
- [ ] Chốt đầu vào tạo, sửa, gửi chạy và yêu cầu hủy experiment.
- [ ] Chốt dữ liệu tiến độ và sự kiện thực thi.
- [ ] Chốt dữ liệu lịch sử thay đổi.
- [ ] Chốt dữ liệu kết quả và thao tác tải tệp.
- [ ] Chốt cách trả danh sách dài.
  - Phân trang, lọc và sắp xếp khi cần.
- [ ] Chốt cấu trúc lỗi thống nhất.
- [ ] Ghi quyền cần thiết cho từng API.
- [ ] Chuẩn bị ví dụ dữ liệu để frontend và mock sử dụng chung.

- **Điều kiện hoàn thành:**
  - Mỗi API có đầu vào, đầu ra, lỗi và quy tắc quyền.
  - Frontend không phải biết cách Coordinator hiện thực thuật toán ES.

## 6. Xây Backend web

### 6.1. Nền tảng và lưu trữ

- [ ] Thiết lập cấu trúc backend và cấu hình chạy cục bộ.
- [ ] Kết nối cơ sở dữ liệu.
- [ ] Tạo cấu trúc dữ liệu đã thiết kế.
- [ ] Thiết lập cách cập nhật cấu trúc cơ sở dữ liệu khi thay đổi.
- [ ] Chuẩn bị dữ liệu mẫu cho người dùng, workspace và membership.
- [ ] Thống nhất cách trả lỗi cho frontend.

### 6.2. Đăng nhập và kiểm tra quyền

- [ ] Hiện thực đăng nhập, đăng xuất và lấy phiên hiện tại.
- [ ] Nếu dùng mật khẩu, lưu dạng băm phù hợp, không lưu mật khẩu nguyên văn.
- [ ] Xác định người dùng từ phiên đăng nhập.
- [ ] Xây phần kiểm tra membership và quyền dùng chung.
- [ ] Áp dụng kiểm tra quyền cho các API liên quan.
- [ ] Xử lý phiên hết hạn và người dùng bị thay đổi quyền.

### 6.3. Workspace và thành viên

- [ ] Hiện thực API xem workspace được phép truy cập.
- [ ] Hiện thực API xem và cập nhật cấu hình theo quyền.
- [ ] Hiện thực API xem thành viên.
- [ ] Hiện thực thay đổi thành viên và vai trò theo phạm vi đã chốt.
- [ ] Hiện thực liên kết tài nguyên với workspace nếu được hỗ trợ.

### 6.4. Experiment

- [ ] Hiện thực API danh sách và chi tiết experiment.
- [ ] Hiện thực tạo và sửa theo quy tắc đã chốt.
- [ ] Kiểm tra cấu hình và quyền sử dụng tài nguyên.
- [ ] Lưu liên kết với mã lần chạy bên Coordinator.
- [ ] Hiện thực API gửi chạy và yêu cầu hủy qua phần giao tiếp Coordinator.
- [ ] Phản ánh đúng kết quả yêu cầu khi mất kết nối.
  - Không tự kết luận thất bại nếu chưa biết Coordinator đã tiếp nhận hay chưa.
- [ ] Hiện thực hàng đợi tại đây nếu đã thống nhất backend web quản lý.

### 6.5. Nhật ký thao tác

- [ ] Ghi thay đổi cấu hình workspace và vai trò.
- [ ] Ghi thao tác tạo, sửa, gửi chạy và yêu cầu hủy experiment.
- [ ] Lưu người thực hiện, thời điểm, đối tượng và kết quả thao tác.
- [ ] Bảo đảm thay đổi dữ liệu và ghi nhật ký không mâu thuẫn khi xảy ra lỗi.
- [ ] Cung cấp API tra cứu nhật ký theo quyền.
- [ ] Loại thông tin bí mật khỏi nhật ký.

### 6.6. Tiến độ và kết quả

- [ ] Cung cấp trạng thái, tiến độ và sự kiện từ Coordinator.
- [ ] Phân biệt dữ liệu mới cập nhật với dữ liệu cũ.
- [ ] Cung cấp danh sách kết quả và tệp đầu ra.
- [ ] Kiểm tra quyền trước khi xem hoặc tải.
- [ ] Hiện thực cách tải tệp từ nơi lưu trữ đã chốt.
- [ ] Xử lý tệp chưa sẵn sàng hoặc không còn tồn tại.

- **Điều kiện hoàn thành:**
  - API hoạt động với dữ liệu lưu bền vững.
  - Không truy cập được dữ liệu workspace khác khi thiếu quyền.
  - Backend có thể chạy với Coordinator giả lập trước khi kết nối thật.

## 7. Xây phần giao tiếp Coordinator

- [ ] Tách phần gọi Coordinator khỏi phần xử lý API của backend web.
- [ ] Quản lý địa chỉ dịch vụ và thời gian chờ bằng cấu hình.
- [ ] Tạo phần giả lập theo hợp đồng đã thống nhất.
- [ ] Hiện thực gọi các thao tác Coordinator hỗ trợ.
- [ ] Kiểm tra dữ liệu phản hồi và chuyển sang định dạng ứng dụng cần.
- [ ] Chuyển lỗi dịch vụ thành lỗi phù hợp cho frontend.
- [ ] Áp dụng quy tắc gửi lại yêu cầu đã thống nhất.
- [ ] Liên kết sự kiện và kết quả với đúng lần chạy.
- [ ] Nếu lưu sự kiện, tránh ghi trùng khi nhận lại cùng sự kiện.
- [ ] Thay phần giả lập bằng kết nối thật khi dịch vụ sẵn sàng.

- **Điều kiện hoàn thành:**
  - Đổi từ giả lập sang dịch vụ thật không yêu cầu viết lại chức năng quản lý workspace.
  - Phần giao tiếp không hiện thực lại thuật toán hoặc cơ chế điều phối ES.

## 8. Thiết kế và xây Frontend

### 8.1. Thiết kế trang và bố cục

- [ ] Kiểm tra các trang và component hiện có để tận dụng.
- [ ] Chốt danh sách trang chính và trang chi tiết.
- [ ] Thiết kế khu vực chọn workspace và thông tin người dùng.
- [ ] Thiết kế điều hướng giữa các trang.
- [ ] Chốt nội dung, dữ liệu và thao tác của từng trang.
- [ ] Thiết kế trạng thái đang tải, trống, lỗi và thiếu quyền.
- [ ] Thống nhất cách hiển thị thời gian, số liệu và trạng thái.
- [ ] Giải thích các thuật ngữ ES bằng tiếng Việt dễ hiểu.
- [ ] Kiểm tra bố cục ở các kích thước màn hình cần hỗ trợ.

### 8.2. Lớp dữ liệu và mock

- [ ] Cập nhật mô tả kiểu dữ liệu theo hợp đồng API.
- [ ] Tập trung các hàm gọi API trong API service — phần giao tiếp backend.
- [ ] Cấu hình địa chỉ API tại một nơi.
- [ ] Xây hook — hàm quản lý dữ liệu trong React — cho các chức năng cần thiết.
- [ ] Tách dữ liệu lưu tạm theo workspace và tham số truy vấn.
- [ ] Xóa dữ liệu người dùng cũ khi đăng xuất hoặc đổi tài khoản.
- [ ] Xử lý cập nhật dữ liệu khi quyền hoặc workspace thay đổi.
- [ ] Dùng mock để mô phỏng thành công, lỗi, trống và mất kết nối.
- [ ] Bảo đảm component không đọc trực tiếp dữ liệu mock.

### 8.3. Các chức năng giao diện

- [ ] Xây đăng nhập, đăng xuất và xử lý phiên hết hạn.
- [ ] Xây chọn workspace và hiển thị vai trò hiện tại.
- [ ] Xây trang cấu hình workspace và thành viên theo quyền.
- [ ] Xây danh sách và chi tiết Worker.
- [ ] Xây danh sách và chi tiết experiment.
- [ ] Xây biểu mẫu tạo và sửa cấu hình theo phạm vi đã chốt.
- [ ] Xây thao tác gửi chạy và yêu cầu hủy.
- [ ] Xây giao diện hàng đợi sau khi thống nhất trách nhiệm.
- [ ] Xây hiển thị tiến độ và chi tiết thực thi cần thiết.
- [ ] Xây lịch sử thay đổi workspace và thao tác experiment.
- [ ] Xây xem kết quả và tải tệp.
- [ ] Ngăn thao tác gửi lặp trong lúc đang xử lý.
- [ ] Hiển thị thao tác theo quyền và xử lý khi backend từ chối.

- **Điều kiện hoàn thành:**
  - Người dùng hoàn thành được các hoạt động đã chọn.
  - Giao diện xử lý được phản hồi lỗi của backend.
  - Truy cập trang bằng URL trực tiếp vẫn được xử lý đúng.

## 9. Kiểm tra tích hợp

- [ ] Kiểm tra đăng nhập, đăng xuất và phiên hết hạn.
- [ ] Kiểm tra các quyền đã chốt cho từng vai trò.
- [ ] Kiểm tra một người có vai trò khác nhau ở các workspace.
- [ ] Kiểm tra truy cập trái quyền bằng API trực tiếp.
- [ ] Kiểm tra dữ liệu còn tồn tại sau khi khởi động lại backend.
- [ ] Kiểm tra thay đổi cấu hình tạo nhật ký đúng.
- [ ] Kiểm tra tạo, gửi chạy và theo dõi cùng một experiment.
- [ ] Kiểm tra yêu cầu hủy và xác nhận dừng là hai bước riêng.
- [ ] Kiểm tra Coordinator mất kết nối hoặc phản hồi quá chậm.
- [ ] Kiểm tra yêu cầu gửi lặp theo quy tắc đã chốt.
- [ ] Kiểm tra kết quả và sự kiện gắn với đúng lần chạy.
- [ ] Kiểm tra tải tệp hợp lệ, thiếu quyền và tệp không tồn tại.
- [ ] Chạy lint — kiểm tra quy tắc code — và build — tạo bản chạy — cho frontend.
- [ ] Ghi kết quả kiểm tra và các giới hạn còn tồn tại.

- **Notes:** tập trung vào hành vi, ranh giới quyền và lỗi có rủi ro; không đặt số lượng bài kiểm tra làm mục tiêu.

## 10. Hướng dẫn chạy và bàn giao

- [ ] Ghi cách chạy frontend và backend cục bộ.
- [ ] Ghi cách khởi tạo dữ liệu và tài khoản thử nghiệm.
- [ ] Ghi cách bật mock hoặc kết nối Coordinator thật.
- [ ] Ghi các cấu hình cần thiết, không đưa giá trị bí mật vào tài liệu.
- [ ] Chuẩn bị một kịch bản sử dụng từ đăng nhập đến xem kết quả.
- [ ] Liệt kê chức năng đã hoàn thành, chưa hỗ trợ và quyết định còn mở.

## 11. Thứ tự thực hiện

| Giai đoạn | Nhóm công việc | Điều kiện chuyển tiếp |
|---|---|---|
| 1. Chốt nền tảng | Phạm vi, quyền và dữ liệu ứng dụng. | Có quy tắc đủ rõ cho hoạt động đầu tiên. |
| 2. Chốt giao tiếp | Hợp đồng Coordinator và hợp đồng frontend. | Có dữ liệu mẫu và hành vi được thống nhất. |
| 3. Xây phần độc lập | Backend lưu trữ, đăng nhập, quyền; frontend và Coordinator giả lập. | Các chức năng chạy được với mock. |
| 4. Kết nối thật | Tích hợp backend, frontend và Coordinator. | Hoàn thành hoạt động từ đầu đến cuối. |
| 5. Kiểm tra và bàn giao | Kiểm tra quyền, lỗi và hướng dẫn chạy. | Có bằng chứng hoạt động và giới hạn rõ ràng. |

- **Hoạt động đầu tiên đề xuất:** đăng nhập → chọn workspace → xem danh sách experiment → xem chi tiết.
- **Hoạt động tiếp theo:** tạo experiment → gửi chạy → theo dõi → xem hoặc tải kết quả.
- **Notes:** hoàn thành từng hoạt động qua các thành phần, không cần hoàn thành toàn bộ backend mới bắt đầu frontend.
- **Cần thống nhất:** trách nhiệm hàng đợi trước khi hoàn thiện chức năng gửi chạy và xếp hàng.

## 12. Tổ chức tài liệu và theo dõi tiến độ

- [x] Tạo `docs/check/` và `docs/uncheck/`.
- [x] Tạo `docs/guide.md` để giải thích bố cục và cách sử dụng tài liệu.
- [x] Tạo `docs/index.md` làm bảng theo dõi tổng.
- [ ] Khi bắt đầu một phần, tạo tài liệu mô tả và checklist chi tiết trong `uncheck/`.
- [ ] Liên kết các tài liệu với mục tương ứng trong checklist tổng.
- [ ] Cập nhật nhiệm vụ đang làm và các điểm còn vướng.
- [ ] Sau khi duyệt, chuyển tài liệu tương ứng sang `check/` và cập nhật liên kết.
- [ ] Chỉ đánh dấu nhiệm vụ hoàn thành khi có bằng chứng phù hợp.
