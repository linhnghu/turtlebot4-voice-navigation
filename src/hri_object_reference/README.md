# Bài 03 — “Pick up this object”: lời nói + chỉ tay

Package ROS 2 Humble **`hri_object_reference`** giải quyết tham chiếu “vật này” bằng cách ghép câu nói với tia chỉ. Mặc định có **ba vật ảo trên màn hình**, lấy hướng ngón trỏ từ **webcam thật** qua MediaPipe và nhận **microphone tiếng Việt** offline qua Vosk. Robot hỏi lại khi mơ hồ/mâu thuẫn.

## Camera + mic tiếng Việt — chạy ngay

Máy này đã có môi trường Python và model tiếng Việt. Chạy:

```bash
cd /home/linh/ros2_ws
./run_object_reference_live.bash
```

Trên máy mới hoặc sau khi thêm source package:

```bash
source /opt/ros/humble/setup.bash
bash src/hri_object_reference/scripts/setup_live.bash
colcon build --symlink-install --packages-select hri_object_reference
./run_object_reference_live.bash
```

Chuẩn bị và sử dụng:

1. Ba vật ảo **đỏ, xanh dương, vàng** xuất hiện sẵn trên bàn trong cửa sổ. Đóng ứng dụng khác đang dùng webcam. Không cần chuẩn bị vật thật.
2. Đưa **một bàn tay** vào ảnh webcam nhỏ ở bên phải, duỗi ngón trỏ và gập các ngón còn lại. Điều chỉnh hướng ngón tay để tia tím trên bàn ảo hướng vào vật muốn chọn; không chĩa thẳng vào ống kính. Tia dùng vector gốc ngón trỏ → đầu ngón trong ảnh, lọc ổn định tối thiểu 0,2 giây, rồi ánh xạ sang khung bàn ảo.
3. Giữ hướng chỉ và nói **“Lấy vật này”**, **“Gắp vật này”**, **“Lấy vật màu đỏ”**, **“Lấy vật màu xanh dương”** hoặc **“Lấy vật màu vàng”**. Giữ tới khi hiện bản chép lời cuối cùng.
4. Khi robot hỏi lại, nói **“màu đỏ”**, **“màu xanh dương”**, **“màu vàng”** hoặc **“xác nhận màu đỏ”**. Xác nhận chỉ có hiệu lực với câu hỏi hiện tại và màu nằm trong các ứng viên. Cũng có thể chỉ lại theo đúng câu lệnh ban đầu.

Giao diện hiển thị bàn ảo, ảnh webcam nhỏ, các tâm vật, tia chỉ, bản chép lời đang nghe/đã nghe, tình trạng camera và mic. Lệnh mô phỏng bằng chuột/text được ẩn trong chế độ live. Nút màu vẫn có thể dùng để xác nhận thủ công khi cần. Đóng cửa sổ để dừng camera và mic.

Tâm và màu vật ảo được trích từ ảnh bàn mô phỏng. Webcam chỉ cần nhận bàn tay để tạo tia chỉ; không yêu cầu tìm ba vật màu trong webcam.

Camera được đưa vào khung vuông bằng letterbox, không lật gương. Tọa độ ngón tay được ánh xạ trực tiếp sang khung bàn ảo vuông; xem tia trên màn hình để điều chỉnh. Đây là điều khiển bằng hướng trong **ảnh 2D**, chưa phải trỏ 3D vào màn hình đã hiệu chuẩn.

Lựa chọn thiết bị và ghi hình:

```bash
./run_object_reference_live.bash camera_index:=0 mic_index:=-1
./run_object_reference_live.bash \
  record_dir:="$PWD/artifacts/hri_object_reference/live/video" \
  log_dir:="$PWD/artifacts/hri_object_reference/live/logs"
```

`mic_index=-1` dùng microphone mặc định của hệ thống. Xem danh sách thiết bị:

```bash
LD_LIBRARY_PATH="$PWD/.hri-runtime/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}" \
  .venv-hri/bin/python -c 'import sounddevice as sd; print(sd.query_devices())'
```

`scene_source:=simulation` là mặc định. Nếu muốn chuyển sang **vật thật**, chạy `./run_object_reference_live.bash scene_source:=camera`, đặt ba vật đỏ/xanh dương/vàng trên nền trơn và hướng webcam nhìn xuống bàn. Chế độ này yêu cầu một vật mỗi màu ổn định qua 3 frame; thiếu màu, nhiều vật cùng màu hoặc che khuất khiến hệ thống chờ. Tâm đo được giữ trong ngưỡng nhiễu 0,025 kích thước ảnh, vật chuyển xa hơn cần ổn định lại và hủy yêu cầu cũ.

Model mặc định là [Vosk Vietnamese small 0.4](https://alphacephei.com/vosk/models), chạy cục bộ; không gửi âm thanh lên dịch vụ ngoài. Có thể đổi bằng `voice_model:=/đường/dẫn/model`. Chỉ kết quả cuối với confidence trung bình ≥0,6 được đưa vào bộ xử lý lệnh; partial chỉ để hiển thị. Không ép mọi âm thanh vào một danh sách lệnh cố định. Hướng dẫn tích hợp mic dựa trên [ví dụ chính thức Vosk](https://github.com/alphacep/vosk-api/blob/master/python/example/test_microphone.py).

Nếu bản chép lời sai, kiểm tra mic đúng thiết bị, nói gần và rõ trong môi trường yên tĩnh. Chỉ báo “mức thu quá lớn” nghĩa là tín hiệu bị clipping: giảm Input Volume trong Sound Settings. Trên máy này đã điều chỉnh từ 100% xuống **35%** sau khi đo clipping. Script không tự đổi âm lượng khi khởi chạy.

Nếu máy bận gây audio overrun hoặc audio trễ quá 0,8 giây, recognizer xóa đoạn cũ; nói lại câu khi chưa thấy bản chép lời cuối. Đóng các demo/ứng dụng xử lý ảnh khác để giảm tải.

## Mô phỏng bằng chuột và text

```bash
cd /home/linh/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select hri_object_reference
./run_object_reference.bash
```

Trong cửa sổ:

1. **Kéo chuột từ phía dưới bàn về phía một vật**, rồi thả để tạo tia chỉ.
2. Chọn/nhập `Pick up this object`, bấm **GỬI LỜI NÓI + TIA ĐANG CHỈ** hoặc Enter trong vòng 3 giây sau khi chỉ.
3. Nếu robot hỏi lại, chỉ lại cho rõ hoặc bấm một màu được bật trong phần xác nhận. Nếu yêu cầu hết hạn, gửi câu nói mới.

Ba nút tình huống dựng sẵn giúp thử nhanh:

| Tình huống | Kết quả mong đợi |
|---|---|
| Chỉ đúng BLUE + “Pick up this object” | `SELECTED`, đánh dấu vật BLUE |
| Chỉ giữa hai vật | `CLARIFY`, hỏi lại, chưa phát target |
| Nói RED nhưng chỉ BLUE | `CLARIFY`, nêu mâu thuẫn RED/BLUE |
| Xác nhận BLUE sau câu hỏi | Chọn BLUE, ghi lý do `explicit_confirmation` |

**ĐỔI VỊ TRÍ CÁC VẬT** đổi màu/vị trí của ảnh rồi nhận dạng lại. Yêu cầu đang chờ và kết quả cũ bị hủy khi cảnh thay đổi; phải chỉ/gửi lệnh mới.

## Demo tự động và sản phẩm nộp bài

```bash
./run_object_reference.bash demo:=true auto_close:=true \
  record_dir:="$PWD/artifacts/hri_object_reference/demo" \
  log_dir:="$PWD/artifacts/hri_object_reference/logs"
```

Demo chạy khoảng 18 giây sau khi kết nối ROS, lần lượt chọn đúng → chỉ giữa hai vật → mâu thuẫn → xác nhận BLUE. Mỗi lần ghi hình tạo thư mục riêng chứa:

- `demo.avi`: video toàn bộ cửa sổ, có tia chỉ và phản hồi; MJPG 10 fps.
- `01_selected.png`, `02_ambiguous.png`, `03_conflict.png`, `04_confirmed.png`: ảnh các tình huống.
- `tabletop.png`, `detected_objects.json`: ảnh đầu vào và vật được trích xuất từ ảnh.
- `dashboard.jsonl`: lời nói, tia chỉ, quyết định và xác nhận từ demo.

`log_dir` lưu `events_<time>.jsonl` của controller, gồm mỗi lần hỏi lại, lý do, request ID, danh sách ứng viên, góc lệch và kết quả xác nhận. `record_dir` cũng dùng được với thao tác thủ công. Đóng cửa sổ/Ctrl-C để hoàn tất file video. Video fps cố định; khi máy chậm, dùng timestamp JSONL để đo thời gian thực. Demo checker tạo thêm MP4 nếu máy có FFmpeg.

Lệnh `run_object_reference.bash` là **mô phỏng ảnh 2D, dùng chuột và text**, không mở camera/mic. Lệnh `run_object_reference_live.bash` dùng camera và mic thật. Kết quả của cả hai chế độ là vật được chọn; package không thực hiện động tác gắp vật lý.

## Cách chọn mục tiêu

`perception.py` tạo ảnh rồi dùng HSV và connected components để trích tâm, màu và kích thước vật. Tâm không được lấy trực tiếp từ tọa độ dùng để vẽ. Mọi tọa độ dùng hệ ảnh vuông chuẩn hóa `[0,1]`: x sang phải, y xuống dưới.

`core.py` phân tích câu nói thành ràng buộc màu và tính góc giữa tia chỉ với hướng từ gốc tia đến từng tâm vật. Chỉ xét vật ở phía trước tia. Vùng chấp nhận gồm cone 12° mỗi phía cộng bán kính góc của vật. Nếu hai ứng viên tốt nhất lệch nhau không quá 8°, robot hỏi lại. Ràng buộc màu không được dùng để che một tia chỉ rõ sang màu khác: nói RED, chỉ BLUE luôn tạo câu hỏi mâu thuẫn.

Câu hỗ trợ gồm `Pick up this object`, `Pick up that one`, `Pick up the red object`, `Select the blue block`, `Gắp vật này`, `Gắp vật đó`, `Chọn vật màu đỏ`, `Lấy vật màu vàng`, hoặc tên màu đơn lẻ. `xanh` chưa rõ nghĩa sẽ bị hỏi lại; dùng `blue`, `xanh dương` hoặc `xanh lam`. Parser dùng ngữ pháp nhỏ, không phải mô hình hiểu ngôn ngữ tự do. Câu phủ định, màu không hỗ trợ và câu không phải lệnh không tạo target.

Lời nói/tia chỉ độc lập được ghép trong **3 giây**. Lệnh có thể đến trước hoặc sau tia. Xác nhận câu hỏi có hạn **15 giây** và phải khớp request ID, ứng viên, cùng cảnh còn mới. Ảnh mặt bàn hết hạn sau **1 giây** không được cập nhật. Mỗi lần chọn chỉ phát target một lần; sau đó cần tia mới cho yêu cầu tiếp theo. Hình học và các thời hạn chỉnh trong `config/reference.yaml`, đọc khi khởi động.

## ROS topics và launch

Runner mặc định đặt `ROS_DOMAIN_ID=68`, `ROS_LOCALHOST_ONLY=1`. Terminal phụ:

```bash
source /opt/ros/humble/setup.bash
source /home/linh/ros2_ws/install/local_setup.bash
export ROS_DOMAIN_ID=68 ROS_LOCALHOST_ONLY=1
ros2 topic echo /reference/state
ros2 topic echo /reference/clarification
ros2 topic echo /reference/target
```

| Topic/service | Kiểu | Nội dung |
|---|---|---|
| `/reference/scene` | `std_msgs/String` | JSON `objects`: danh sách `{id,color,x,y,radius}`; camera hoặc dashboard là nguồn, tùy chế độ |
| `/reference/pointing` | `std_msgs/String` | JSON `{origin:[x,y],direction:[dx,dy]}`; vector hữu hạn, khác 0 |
| `/reference/speech` | `std_msgs/String` | Text thuần hoặc JSON `{text,confidence,accepted:true}` từ STT |
| `/reference/transcript` | `std_msgs/String` | Bản chép lời partial/final và kết quả lọc confidence |
| `/reference/image/compressed` | `sensor_msgs/CompressedImage` | Khung webcam vuông, có landmark bàn tay |
| `/reference/camera_status` | `std_msgs/String` | Sức khỏe camera, cảnh sẵn sàng, vật đo được, ray và số bàn tay |
| `/reference/mic_status` | `std_msgs/String` | Sức khỏe mic, mức tín hiệu, clipping, số block và model |
| `/reference/request` | `std_msgs/String` | Snapshot nguyên tử `{text,ray}`; `ray:null` xóa tia cũ và đợi chỉ mới |
| `/reference/confirm` | `std_msgs/String` | JSON `{request_id,object_id}`; chỉ dùng khi đang CLARIFY |
| `/reference/state` | `std_msgs/String` | Trạng thái, lý do, target, ứng viên, góc lệch, IDs và các vật; 20 Hz |
| `/reference/events` | `std_msgs/String` | Mỗi lần quyết định thay đổi |
| `/reference/clarification` | `std_msgs/String` | Mỗi lần hỏi lại, gồm message và ứng viên |
| `/reference/target` | `std_msgs/String` | Vật đã chọn với tâm/màu, request ID và lý do; một event mỗi lần chọn |
| `/reference/reset` | `std_srvs/Trigger` | Xóa yêu cầu/tia cũ, làm mất hiệu lực xác nhận cũ |

Ví dụ gửi hai kênh đồng thời để không bị thứ tự callback giữa các topic ảnh hưởng:

```bash
ros2 topic pub --once /reference/request std_msgs/msg/String \
  '{data: "{\"text\":\"Pick up this object\",\"ray\":{\"origin\":[0.5,0.9],\"direction\":[0,-1]}}"}'
```

Chạy controller không GUI để nối nguồn ngoài: `./run_object_reference.bash gui:=false`. Nguồn ngoài phải cung cấp cảnh đều đặn, cùng hệ tọa độ vuông chuẩn hóa. Đổi domain bằng `REFERENCE_DOMAIN_ID=69 ./run_object_reference.bash`. Truyền cấu hình bằng `config:=/đường/dẫn/reference.yaml`.

## Kiểm tra và giới hạn

```bash
source /opt/ros/humble/setup.bash
source install/local_setup.bash
colcon test --packages-select hri_object_reference --event-handlers console_direct+
colcon test-result --test-result-base build/hri_object_reference --verbose
ROS_DOMAIN_ID=169 ROS_LOCALHOST_ONLY=1 python3 src/hri_object_reference/test/check_runtime.py
ROS_DOMAIN_ID=170 ROS_LOCALHOST_ONLY=1 python3 src/hri_object_reference/test/check_demo.py
# Khi live launch đang chạy ở domain 68:
ROS_DOMAIN_ID=68 ROS_LOCALHOST_ONLY=1 python3 src/hri_object_reference/test/check_live_smoke.py
```

Runtime checker tự chạy controller với GUI tắt và kiểm tra DDS/service. Demo checker chạy cửa sổ thật, quay video và kiểm tra event chọn/hỏi lại qua ROS. Xem kết quả đã xác minh trong `VALIDATION.md`.

Ngưỡng HSV áp dụng cho cả ảnh mô phỏng và webcam, chưa được hiệu chỉnh cho mọi loại ánh sáng/camera. `radius` là xấp xỉ theo kích thước component ảnh; không có chiều sâu, phục hồi vật bị che khuất, hiệu chuẩn tay–camera 3D hoặc danh tính vật qua chuyển động. Khi đổi bố cục, phải tạo yêu cầu mới. Trường hợp cần hiểu câu tự do hoặc gắp bằng robot cần adapter bổ sung.

Nếu không thấy topic, kiểm tra cùng domain và đã source workspace. Nếu thiếu PyQt5/OpenCV, cài dependency qua rosdep (`rosdep install --from-paths src/hri_object_reference --ignore-src -r -y`). Runner dùng Python hệ thống có ROS và dọn biến loader của VS Code Snap. Khi không có màn hình, đặt `QT_QPA_PLATFORM=offscreen` để chạy demo/kiểm tra giao diện ngoài màn hình.
