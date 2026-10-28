# Brief thiết kế giao diện chính HeteroES — gửi Claude

> Có thể gửi nguyên file này cho Claude. Đây là brief thiết kế giao diện sản phẩm, tập trung vào bố cục, màn hình, điều hướng, breadcrumb và tương tác.

## 1. Yêu cầu dành cho Claude

Hãy thiết kế **toàn bộ giao diện chính của HeteroES**, nền tảng thực hiện và theo dõi thí nghiệm post-training mô hình ngôn ngữ bằng **Evolution Strategies (ES)** trên các máy có GPU khác nhau.

“Giao diện chính” ở đây gồm khung ứng dụng, các mục điều hướng chính và những trang chi tiết bên trong chúng. Dashboard là trang tổng quan trong giao diện này. Người dùng cần đi từ tổng quan đến experiment, generation, candidate và attempt mà vẫn hiểu mình đang ở đâu thông qua breadcrumb.

**Loại khỏi phạm vi:** đăng nhập, đăng ký, khôi phục mật khẩu, tài khoản/hồ sơ người dùng, workspace người dùng, thành viên, vai trò và phân quyền. Không thêm màn hình hoặc thành phần liên quan đến các hệ thống này vào sidebar, topbar hay prototype.

Tôi muốn một phương án thiết kế cụ thể, nhất quán và có thể làm cơ sở triển khai frontend. Hãy tập trung vào trải nghiệm sử dụng, nội dung và tương tác. Nếu công cụ hỗ trợ, tạo prototype tương tác để thử các luồng chính. Khi mở prototype, vào thẳng giao diện chính.

## 2. Bối cảnh và mục tiêu

HeteroES phục vụ nhóm nghiên cứu hoặc nhóm làm dự án chạy thí nghiệm LLM trên cụm GPU nhỏ. Các máy có thể khác nhau về VRAM và tốc độ xử lý. Ví dụ phần cứng mục tiêu: RTX 5070 Ti 16 GB và GTX 1660 Super 6 GB.

Một cấu hình khởi đầu là mô hình `Qwen2.5-0.5B-Instruct` với bài toán `Countdown`. Có thể dùng cấu hình này làm ví dụ, không coi là lựa chọn cố định của mọi thí nghiệm.

Người dùng cần:

- Nắm tình trạng cụm GPU và experiment đang chạy.
- Xem worker nào được tham gia tính toán và lý do.
- Theo dõi tiến độ từ experiment xuống generation, candidate và attempt.
- Tìm sự kiện lỗi và lần thực hiện liên quan để điều tra.
- Xem cấu hình, kết quả và tệp đầu ra của experiment.

Thông tin cơ bản phải dễ đọc; chi tiết kỹ thuật nên mở theo nhu cầu.

## 3. Thuật ngữ cần thể hiện đúng

| Khái niệm | Ý nghĩa đối với người dùng |
|---|---|
| Experiment | Một thí nghiệm có tên, cấu hình và thông tin thực thi. |
| Generation | Một vòng của thuật toán ES, gồm nhiều candidate cần đánh giá. |
| Candidate | Một phương án nhiễu/biến thể được đánh giá trong một generation. |
| Attempt | Một lần thực hiện công việc của candidate trên worker; khác với candidate. |
| Worker | Tiến trình trên máy GPU thực hiện công việc được giao. |
| Admission | Quyết định worker có được tham gia và có giới hạn gì. |
| Coordinator | Thành phần điều phối và xác nhận trạng thái thực thi. |
| Artifact | Tệp gắn với experiment: cấu hình, checkpoint, manifest hoặc kết quả đánh giá. |
| Reward | Điểm đánh giá theo bài toán; không mặc định là độ chính xác hoặc phần trăm. |

Giữ thuật ngữ quen thuộc như Experiment, Worker, Generation, Candidate; dùng mô tả/tooltip tiếng Việt để giải thích. Nội dung hướng dẫn và thông báo ưu tiên tiếng Việt.

## 4. Khung ứng dụng và điều hướng

Thiết kế một khung thống nhất cho tất cả các trang:

- **Sidebar:** thương hiệu HeteroES, mô tả ngắn; các mục Dashboard, Experiments, Workers, Events, Artifacts.
- **Topbar:** tiêu đề hoặc ngữ cảnh trang, trạng thái kết nối nguồn dữ liệu, thời điểm cập nhật và làm mới khi phù hợp.
- **Nội dung:** tiêu đề trang, breadcrumb ở các trang con, hành động liên quan và dữ liệu.

Sidebar cần thể hiện đúng mục cha đang được chọn khi mở trang con. Breadcrumb có các cấp cha bấm được, cấp hiện tại rõ ràng và không quá dài. Với ID dài, rút gọn cách hiển thị nhưng có thể xem/sao chép đầy đủ.

Các tuyến điều hướng cần thiết kế:

- Dashboard → Experiment → Generation → Candidate → thông tin Attempt.
- Experiments → Chi tiết Experiment → Generation → Candidate.
- Workers → Chi tiết Worker.
- Events → Chi tiết sự kiện hoặc panel → đối tượng liên quan.
- Artifacts → Thông tin tệp hoặc panel; có liên kết về experiment.

Attempt có thể nằm trong trang Candidate hoặc panel bên trong trang đó. Không bắt buộc tạo thêm một trang riêng nếu không giúp trải nghiệm.

Tìm kiếm và bộ lọc nằm gần danh sách tương ứng. Không cần thêm tìm kiếm toàn hệ thống.

## 5. Nội dung và tương tác từng màn hình

### A. Dashboard — tổng quan

Mục tiêu: giúp người dùng nắm tình hình hiện tại và biết nơi cần đi tiếp.

- Chỉ số: experiment đang chạy; worker đang hoạt động trên tổng số; worker được admission; lỗi/cảnh báo trong khoảng thời gian rõ ràng.
- Experiment đang chạy/gần đây: tên, trạng thái, mô hình, generation hiện tại và tiến độ candidate của generation đó.
- Tóm tắt worker: GPU, VRAM, trạng thái hoạt động và admission.
- Sự kiện gần đây: mức độ, thời gian, nội dung và liên kết đối tượng liên quan.
- Các liên kết mở danh sách đầy đủ hoặc trang chi tiết tương ứng.

Chỉ số tổng quan phải khớp dữ liệu và phạm vi thống kê. Worker online không đồng nghĩa với worker được admission. Biểu đồ chỉ thêm khi có mục đích và nguồn dữ liệu phù hợp.

### B. Experiments — danh sách

- Bảng gồm tên, trạng thái, mô hình/phiên bản, chính sách lập lịch, generation hiện tại và thời gian tạo.
- Tìm theo tên/ID, lọc trạng thái, sắp xếp thời gian.
- Mở chi tiết qua tên hoặc vùng tương tác rõ ràng.
- Phân biệt chưa có experiment với không có kết quả phù hợp bộ lọc.
- Có lối vào tạo experiment nếu đưa luồng dự kiến ở mục G vào prototype.

### C. Chi tiết Experiment — màn hình trọng tâm

- Breadcrumb: Experiments → tên experiment.
- Header: tên, ID có thể sao chép, trạng thái, mô hình và phiên bản.
- Tóm tắt: chính sách lập lịch, chế độ đồng bộ, thời gian tạo/bắt đầu/kết thúc, generation hiện tại.
- Tiến độ: số candidate committed trên tổng số của generation hiện tại.
- Các tab/vùng: Tổng quan, Generations, Cấu hình, Events, Artifacts. Có thể điều chỉnh cách tổ chức nếu vẫn giữ ngữ cảnh.
- Bảng generations: ID, trạng thái, phiên bản mô hình, tiến độ candidate, reward trung bình/tốt nhất và thời gian.
- Biểu đồ reward theo generation khi có dữ liệu; ghi rõ trục và ý nghĩa các đường.
- Events và Artifacts được lọc trong ngữ cảnh experiment, liên kết đến chi tiết liên quan.

Ghi rõ “Tiến độ generation hiện tại”. Không dùng tỷ lệ candidate của một generation để biểu thị phần trăm hoàn thành toàn experiment khi chưa biết tổng số generation. Nếu chưa có generation hoặc reward, thể hiện thiếu dữ liệu trung thực.

### D. Chi tiết Generation

- Breadcrumb: Experiments → experiment → generation.
- Hiển thị trạng thái, phiên bản mô hình, tiến độ candidate, reward và thời gian.
- Danh sách candidate: ID, trạng thái, worker được giao và attempt liên quan khi có dữ liệu.
- Nhấn candidate để mở chi tiết, giữ đường quay lại generation.
- Có thể có vùng chuyên sâu cho thời gian, mạng và đồng bộ khi dữ liệu được cung cấp.

Không ép generation ID thành số thứ tự nếu hệ thống không cung cấp số thứ tự đó.

### E. Chi tiết Candidate và Attempt

- Breadcrumb: Experiments → experiment → generation → candidate.
- Thông tin chính: ID, trạng thái, phiên bản mô hình, worker được giao.
- Thông tin kỹ thuật có thể thu gọn: seed, batch IDs, hash cấu hình và lease deadline.
- Attempt: ID, worker, trạng thái, thời gian bắt đầu/kết thúc và loại lỗi nếu có.
- Nếu chưa có attempt, hiển thị “Chưa bắt đầu thực hiện”. Nếu tải attempt lỗi, giữ thông tin candidate còn đọc được.
- Chỉ thiết kế lịch sử nhiều attempt khi backend cung cấp; không tự dựng lịch sử từ một attempt hiện tại.

Các trạng thái candidate cần giải thích:

- `PENDING`: chờ được giao.
- `LEASED`: đã được cấp quyền thực hiện trong thời hạn.
- `RUNNING`: đang thực hiện.
- `COMMITTED`: kết quả đã được hệ thống chấp nhận.

Không đồng nhất “worker đã tính xong” với “kết quả đã được chấp nhận”. Không cần hiển thị lease token trong giao diện thông thường.

### F. Workers — danh sách và chi tiết

**Danh sách:** worker ID, GPU, VRAM, trạng thái hoạt động, admission, heartbeat; tìm/lọc theo worker, trạng thái và admission.

**Chi tiết:** breadcrumb Workers → worker; hồ sơ GPU, VRAM tổng/còn trống, throughput và safe chunk size khi có dữ liệu, heartbeat, admission và lý do.

Admission cần biểu đạt được bốn tình huống: không đủ điều kiện; đủ điều kiện nhưng không có lợi; được tham gia có giới hạn; được tham gia đầy đủ.

Trạng thái hoạt động và admission là hai thông tin riêng: một worker online vẫn có thể không được đưa vào tính toán. Không thêm nút bật/tắt máy, điều chỉnh GPU, phân công candidate hoặc thay đổi admission thủ công.

### G. Tạo/cấu hình và thao tác Experiment — luồng dự kiến

Có thể thiết kế luồng này để thể hiện trải nghiệm trong giao diện chính, nhưng **các thao tác và trường cấu hình chưa được coi là đã có backend hỗ trợ**. Ghi rõ giả định trong phần bàn giao.

- Đề xuất biểu mẫu/wizard ngắn: Thông tin → Cấu hình → Kiểm tra và gửi.
- Tên experiment, mô hình, chính sách lập lịch và chế độ đồng bộ; lựa chọn cần khớp cấu hình hệ thống hỗ trợ.
- Giải thích ngắn các lựa chọn, lỗi nhập liệu và trạng thái gửi.
- Sau khi gửi, phân biệt “đã tiếp nhận yêu cầu” với “đang chạy”.
- Nếu thiết kế yêu cầu hủy trong chi tiết experiment: có xác nhận đối tượng, trạng thái gửi, đã tiếp nhận và trạng thái thực thi chính thức sau cập nhật.

Không thêm lịch chạy, pause/resume, retry thủ công hoặc xóa experiment như chức năng đã chốt. Trong prototype có thể mô phỏng gửi/chạy/hủy, ghi rõ phần mô phỏng trong bàn giao.

### H. Events — nhật ký thực thi

- Danh sách/timeline có thời gian, mức độ INFO/WARNING/ERROR, loại sự kiện và nội dung.
- Bộ lọc theo mức độ, thời gian và đối tượng liên quan.
- Nội dung ngắn để quét nhanh; panel hoặc vùng mở rộng cho chi tiết kỹ thuật.
- Liên kết về experiment, generation, candidate, attempt hoặc worker khi có ngữ cảnh.
- Khi mở từ experiment, giữ bộ lọc và ngữ cảnh tương ứng.
- Khi cập nhật tự động, tránh cuộn cưỡng bức và giữ vị trí đọc.

### I. Artifacts — tệp và kết quả

- Danh sách gồm tên, loại, experiment liên quan, thời gian tạo và kích thước khi có dữ liệu.
- Lọc theo experiment/loại tệp; liên kết về experiment.
- Xem metadata trong panel hoặc trang con có breadcrumb nếu cần.
- Tải tệp khi hệ thống cung cấp đường tải hợp lệ.
- Xử lý tệp chưa sẵn sàng, không còn tồn tại và lỗi tải.

Đường dẫn lưu trữ đơn thuần không được giả định là URL tải hợp lệ. Các loại tệp có thể minh họa: cấu hình, checkpoint, manifest, kết quả đánh giá.

## 6. Hướng thiết kế thị giác

Đề xuất phong cách **giao diện nghiên cứu hiện đại**, gọn, rõ và có mật độ thông tin vừa đủ để sử dụng lâu dài.

- Ưu tiên nền sáng, bề mặt trung tính và một màu nhấn nhất quán.
- Typography dễ đọc; dùng monospace cho ID hoặc giá trị kỹ thuật khi phù hợp.
- Phân cấp rõ giữa tên đối tượng, chỉ số chính, dữ liệu phụ và hành động.
- Badge có nhãn chữ; không dùng màu làm dấu hiệu duy nhất.
- Bảng, biểu đồ, tab, breadcrumb, form và dialog cùng một hệ thống thị giác.
- Dùng bảng cho thông tin cần so sánh; tránh chia mọi dữ liệu thành card rời.
- Có trạng thái hover, focus, selected, disabled và loading; hỗ trợ bàn phím và độ tương phản phù hợp.

Ưu tiên desktop 1440 px, thích ứng với laptop 1024 px và mobile khoảng 390 px. Trên màn hình hẹp, sidebar có thể thu gọn, breadcrumb cần xử lý chiều dài, thông tin phụ có thể mở thêm và bảng có thể cuộn có kiểm soát.

Hãy chọn palette, typography, spacing và icon cụ thể; giải thích ngắn các lựa chọn quan trọng.

## 7. Trạng thái giao diện cần thiết kế

| Tình huống | Trải nghiệm mong muốn |
|---|---|
| Đang tải lần đầu | Skeleton phù hợp với cấu trúc trang/khu vực. |
| Chưa có dữ liệu | Giải thích ngắn và bước tiếp theo phù hợp. |
| Bộ lọc không có kết quả | Cho xóa hoặc điều chỉnh bộ lọc. |
| Lỗi một khu vực | Giữ phần còn đọc được; cho thử lại khu vực lỗi. |
| Mất kết nối/cập nhật thất bại | Giữ dữ liệu cũ nếu có, ghi thời điểm cập nhật và cho thử lại. |
| Thiếu trường tùy chọn | Dùng “Chưa có dữ liệu” hoặc dấu gạch; không biến thành số 0. |
| Không tìm thấy đối tượng | Thông báo rõ, có lối về danh sách hoặc cấp cha. |
| Đang gửi thao tác | Tránh gửi lặp; báo trạng thái tiếp nhận và lỗi có thể xử lý. |

Thời gian cần dễ đọc và có múi giờ rõ. Không tự suy ra worker đã chết chỉ từ heartbeat cũ khi chưa có quy tắc chính thức. Mất kết nối nguồn dữ liệu không đồng nghĩa mọi worker đã offline.

## 8. Dữ liệu demo cho prototype

Dùng dữ liệu nhất quán xuyên suốt các màn hình:

- Hai worker có GPU khác nhau; minh họa online được admission và online không được admission, có lý do.
- Một experiment đang chạy, một đã hoàn tất, một có sự kiện lỗi.
- Một generation có candidate PENDING, LEASED, RUNNING và COMMITTED.
- Một candidate có attempt lỗi để thử luồng điều tra; không tự đặt candidate vào trạng thái FAILED vì tập trạng thái candidate hiện tại không có giá trị đó.
- Các sự kiện liên kết đúng ID của đối tượng tương ứng.
- Một số artifact gắn với experiment.
- Nếu có biểu đồ reward, dùng chuỗi generation của cùng experiment.

Ghi rõ toàn bộ là **dữ liệu demo**, không phải benchmark. Chỉ số Dashboard phải khớp với dữ liệu danh sách và khoảng thời gian thống kê. Không tạo GPU utilization, chi phí hoặc tốc độ cải thiện mô hình rồi coi là dữ liệu sẵn có.

## 9. Các giả định cần ghi trong bàn giao

Không cần chặn việc dựng thiết kế; dùng giả định tối thiểu và ghi rõ:

- Trạng thái chính thức của experiment, generation, worker và attempt.
- Một experiment có một hay nhiều lần chạy; không tự thêm cấp Run vào điều hướng khi chưa chốt.
- Trường cấu hình và các thao tác tạo/gửi chạy/hủy được hỗ trợ.
- Dữ liệu metric và lịch sử attempt có thể cung cấp.
- Cơ chế cập nhật tiến độ và cách tải artifact.

Không mở rộng phạm vi sang hệ thống người dùng hoặc workspace để giải quyết các giả định này.

## 10. Kết quả tôi muốn nhận từ Claude

1. Một phương án giao diện chính hoàn chỉnh và sơ đồ điều hướng ngắn.
2. Thiết kế Dashboard, Experiments, chi tiết Experiment, Generation, Candidate/Attempt, Workers/chi tiết Worker, Events và Artifacts.
3. Breadcrumb và tương tác chuyển trang nhất quán; tab/panel giữ đúng ngữ cảnh đối tượng.
4. Luồng tạo/gửi experiment và yêu cầu hủy nếu đưa vào prototype, với giả định hỗ trợ được ghi rõ.
5. Bộ thành phần dùng chung và cách thích ứng desktop/laptop/mobile.
6. Prototype tương tác nếu công cụ hỗ trợ; nếu không, wireframe và mô tả tương tác cụ thể.
7. Ghi chú bàn giao: dữ liệu cần, thao tác cần backend và các quyết định cần xác nhận.

Các luồng cần thử được:

- Dashboard → Experiment → Generation → Candidate → xem Attempt → quay lại bằng breadcrumb.
- Experiments → tìm/lọc → chi tiết Experiment → Events hoặc Artifacts trong ngữ cảnh experiment.
- Workers → lọc → chi tiết Worker → đọc lý do admission → quay lại danh sách.
- Events → lọc lỗi → mở đối tượng liên quan.
- Artifacts → lọc → xem metadata → tải demo hoặc xem trạng thái chưa thể tải.
- Nếu có luồng dự kiến: tạo experiment → kiểm tra → gửi yêu cầu → xem trạng thái tiếp nhận.
- Xem các trạng thái trống, lỗi và dữ liệu cũ; thử làm mới/thử lại.

## 11. Tiêu chí đánh giá

- Người dùng nắm được tình trạng hệ thống từ Dashboard và đi sâu vào đối tượng cần theo dõi.
- Breadcrumb thể hiện đúng quan hệ experiment → generation → candidate và cho quay lại dễ dàng.
- Sidebar, tab và panel giữ đúng ngữ cảnh khi chuyển giữa các trang.
- Hoạt động của worker và admission được phân biệt rõ.
- Tiến độ generation không gây hiểu nhầm về tiến độ toàn experiment.
- Kết quả được chấp nhận, yêu cầu thao tác và trạng thái thực thi chính thức được phân biệt.
- Dữ liệu thiếu, dữ liệu cũ và lỗi được thể hiện trung thực.
- Các trang cùng ngôn ngữ thiết kế và dùng được ở các kích thước màn hình yêu cầu.
- Prototype mở thẳng vào giao diện chính và giữ phạm vi đã nêu.

**Hãy bắt đầu bằng một phương án thiết kế và prototype giao diện chính cụ thể dựa trên brief này.**
