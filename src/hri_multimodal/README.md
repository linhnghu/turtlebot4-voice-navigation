# Bài 01 — Robot nhận lệnh bằng giọng nói và cử chỉ

Package ROS 2 Humble độc lập `hri_multimodal`, có hai chế độ: **Gazebo Fortress + nhận cử chỉ webcam thật** và mô phỏng động học 2D nhẹ bằng Python/Qt. Không phụ thuộc các package TurtleBot; không cần Nav2.

[Kết quả kiểm chứng](VALIDATION.md): 46 unit test, 16 kiểm tra runtime 2D và 13 kiểm tra physics Gazebo. Video 48 giây cũ minh họa chế độ 2D; bằng chứng Gazebo ở `artifacts/hri_multimodal/gazebo_validation/`.

## Chạy nhanh — Gazebo và webcam

```bash
cd /home/linh/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select hri_multimodal --symlink-install
bash src/hri_multimodal/scripts/setup_camera.bash
./run_hri_gazebo.bash
```

Lệnh cuối mở Gazebo, dashboard và cửa sổ webcam. Robot hai bánh có khối lượng, ma sát, va chạm và odometry từ DiffDrive, trong phòng 8 × 6 m. Bảng 2D phản ánh vị trí Gazebo thực; không chạy simulator động học song song. Người gọi màu vàng trong Gazebo di chuyển theo điểm bấm trên dashboard. Vị trí này là mục tiêu đặt thủ công, không được suy ra từ vị trí người trong webcam.

- **Thumb Up**: giơ ngón cái rõ trong ít nhất 0.2 giây → tiến.
- **Wave**: xòe bàn tay và vẫy ngang trái–phải ít nhất ba lượt trong 1.5 giây → lại đây.
- **Open Palm đứng yên**: giữ tay xòe 0.4 giây → STOP và giữ chốt. Ngay khi phát hiện bàn tay xòe chưa phân loại, vận tốc bị khóa về 0; không chờ 0.4 giây để ngừng chuyển động.
- Hạ tay rồi bấm **RESET STOP** và gửi lệnh mới. Không reset khi Open Palm còn nhìn thấy hoặc camera đã mất.
- Tránh để hai người cùng ra dấu: nhiều bàn tay khóa chuyển động; Open Palm vẫn dừng.
- Cử chỉ được cập nhật liên tục. Sau khi hạ tay, lệnh gần nhất có hiệu lực tối đa 3 giây. Lệnh nói cũng có thời hạn 3 giây.

MediaPipe cung cấp Thumb Up/Open Palm và landmarks; Wave là phân loại chuyển động theo thời gian từ landmarks, không phải một nhãn tĩnh có sẵn. Trong giai đoạn xác định Wave, robot đứng yên; nếu đã nhận Open Palm và chốt STOP thì Wave không tự mở chốt.

Ở chế độ webcam, dropdown cử chỉ bị khóa; nút gửi chỉ cập nhật lời nói, không ghi đè tín hiệu từ camera. Nút dừng khẩn vẫn hoạt động. Thiếu frame camera quá 0.6 giây hoặc camera báo lỗi: dừng và giữ chốt. Gazebo adapter tự gửi vận tốc 0 nếu controller im lặng quá 0.3 giây hoặc odometry quá hạn 0.5 giây. Một tiến trình quan trọng thoát sẽ đóng toàn bộ launch. Tốc độ tiến mặc định Gazebo là 0.35 m/s; controller giới hạn chuyển động gần tường.

Bật cả microphone trong cùng launch (sau khi đã setup voice):

```bash
./run_hri_gazebo.bash voice:=true
```

Tùy chọn:

```bash
# Chọn webcam khác:
./run_hri_gazebo.bash camera_index:=2
# Chỉ thử physics bằng nhãn cử chỉ mô phỏng:
./run_hri_gazebo.bash camera:=false
# Headless để kiểm thử ROS/Gazebo:
./run_hri_gazebo.bash camera:=false gazebo_gui:=false dashboard:=false
```

Mặc định ROS domain 66, Gazebo partition `hri_${USER}_66`. Không chạy bản 2D và Gazebo cùng domain đồng thời; đóng launch cũ bằng Ctrl+C trước. Có thể chọn domain khác bằng `HRI_DOMAIN_ID=70 ./run_hri_gazebo.bash`. Script tạo môi trường native Qt để tránh xung đột Snap.

## Chạy mô phỏng 2D nhẹ

```bash
cd /home/linh/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select hri_multimodal --symlink-install
./run_hri_demo.bash
```

Chọn câu nói, chọn nhãn cử chỉ, chỉnh độ tin cậy và bấm **GỬI HAI KÊNH**. Robot và vết di chuyển hiển thị trong phòng 8 × 6 m. Bấm trong bản đồ để đặt vị trí người gọi cho lệnh **Come here**. Mỗi lần gửi cho phép thực hiện lệnh trong tối đa 3 giây; gửi lại để tiếp tục. Nút **DỪNG KHẨN** luôn gửi Stop và Open Palm. Sau STOP, bấm **RESET STOP**, rồi gửi một lệnh mới.

Chế độ `run_hri_demo.bash` dùng văn bản thay lời nói và **nhãn cử chỉ mô phỏng**. Dùng `run_hri_gazebo.bash` ở phần trên để nhận bàn tay webcam thật. Nhận giọng nói thật qua microphone có adapter tùy chọn ở phần dưới.

Script chạy mặc định dùng `ROS_DOMAIN_ID=66`, `ROS_LOCALHOST_ONLY=1`. Các topic vận tốc đều nằm trong `/hri`, dành riêng cho mô phỏng.

## Quy tắc kết hợp

Hàm thuần Python trong `hri_multimodal/fusion.py`:

```python
fusion_decision(intent, gesture, conf_voice, conf_gesture)
# -> Decision(action, reason)
```

| Lời nói | Cử chỉ tương ứng | Hành động |
|---|---|---|
| Move forward / Đi thẳng / Tiến lên | Thumb Up | Tiến theo hướng hiện tại |
| Come here / Lại đây | Wave | Quay và đến cách người gọi 0.4 m |
| Stop / Dừng / Dừng lại | Open Palm | Dừng, giữ chốt STOP |

- Chuẩn hóa hoa/thường, dấu tiếng Việt, dấu câu và dấu gạch dưới. Chỉ nhận câu trùng danh sách; câu như `do not move forward` không trở thành lệnh tiến.
- STOP ở **bất kỳ kênh nào với confidence > 0** thắng mọi lệnh chuyển động, kể cả khi confidence dưới ngưỡng chuyển động.
- Chuyển động cần confidence **≥ 0.65**. Hai kênh hợp lệ trùng nhau thì thực hiện; một kênh hợp lệ cũng có thể thực hiện.
- Hai lệnh chuyển động hợp lệ khác nhau: dừng và giữ chốt. Không chọn ngẫu nhiên một kênh.
- Không có tín hiệu đáng tin hoặc hết hạn: đứng yên, không giữ chốt. Confidence = 0 nghĩa là bỏ tín hiệu đó.
- JSON lỗi, sai schema hoặc confidence không hữu hạn/ngoài [0,1]: dừng và giữ chốt.
- Reset xóa cả chốt và tín hiệu cũ. Lệnh mới không tự mở chốt STOP.
- Mất pose quá 0.5 giây: controller không phát vận tốc di chuyển. Mất `/hri/cmd_vel` quá 0.3 giây: simulator tự đứng yên. Robot có bán kính 0.22 m và bị chặn tại biên phòng.

Hai chế độ dùng để học HRI; chốt STOP phần mềm không phải bộ dừng khẩn phần cứng.

## Các node và giao tiếp ROS 2

```text
dashboard ── /hri/input ──▶ fusion_node ── /hri/cmd_vel ──▶ simulator
                                ▲                            │
voice_node ── /hri/voice ────────┤◀──────── /hri/pose ────────┘
                                └── /hri/decision ──▶ dashboard
```

| Topic/service | Kiểu | Nội dung |
|---|---|---|
| `/hri/input` | `std_msgs/msg/String` | Snapshot JSON thay cả hai kênh cùng lúc; kênh bỏ trống được xóa |
| `/hri/voice` | `std_msgs/msg/String` | JSON cập nhật riêng lời nói |
| `/hri/gesture` | `std_msgs/msg/String` | JSON cập nhật riêng cử chỉ |
| `/hri/cmd_vel` | `geometry_msgs/msg/Twist` | Vận tốc riêng cho simulator |
| `/hri/pose` | `geometry_msgs/msg/Pose2D` | Vị trí robot, m và rad |
| `/hri/target` | `geometry_msgs/msg/Point` | Vị trí người gọi trong phòng |
| `/hri/decision` | `std_msgs/msg/String` | JSON hành động, lý do, chốt STOP, vận tốc và tín hiệu còn hạn |
| `/hri/camera_status` | `std_msgs/msg/String` | Sức khỏe camera, nhãn nhận dạng và khóa chuyển động tạm thời |
| `/hri/camera/image/compressed` | `sensor_msgs/msg/CompressedImage` | Ảnh webcam có landmarks/nhãn, khoảng 5 Hz |
| `/hri/gazebo/odom` | `nav_msgs/msg/Odometry` | Odometry bánh xe từ Gazebo |
| `/hri/gazebo/world_poses` | `tf2_msgs/msg/TFMessage` | Pose ground truth của scene, dùng kiểm chứng physics; không thay thế TF |
| `/hri/reset_stop` | `std_srvs/srv/Trigger` | Xóa STOP và tín hiệu cũ |

Trong terminal khác:

```bash
cd /home/linh/ros2_ws
source /opt/ros/humble/setup.bash
source install/local_setup.bash
export ROS_DOMAIN_ID=66 ROS_LOCALHOST_ONLY=1
ros2 topic echo /hri/decision
# Snapshot đồng thời, gửi một lần:
ros2 topic pub --once /hri/input std_msgs/msg/String \
  '{data: "{\"voice\":{\"text\":\"Move forward\",\"confidence\":0.95},\"gesture\":{\"text\":\"Open Palm\",\"confidence\":0.9}}"}'
ros2 service call /hri/reset_stop std_srvs/srv/Trigger '{}'
# Chỉ cập nhật một kênh:
ros2 topic pub --once /hri/voice std_msgs/msg/String \
  '{data: "{\"text\":\"Come here\",\"confidence\":0.95}"}'
```

Gửi snapshot qua `/hri/input` khi hai kênh thuộc cùng một mẫu thử; cách này tránh ghép một nửa mẫu mới với mẫu cũ. Hai topic riêng dành cho nguồn bất đồng bộ, sử dụng tín hiệu mới nhất còn hạn của mỗi kênh. Thời hạn dùng đồng hồ monotonic và thời điểm nhận tại controller.

Chạy không GUI: `./run_hri_demo.bash gui:=false`. Đổi thời hạn: `./run_hri_demo.bash input_ttl:=5.0` (dòng gợi ý trong GUI vẫn mô tả giá trị mặc định 3 giây).

## Demo 48 giây và bằng chứng

```bash
./run_hri_demo.bash demo:=true \
  record_dir:=/home/linh/ros2_ws/artifacts/hri_multimodal
```

Demo tự gửi các tình huống trùng khớp, Open Palm ưu tiên, cố chuyển động khi đang giữ STOP, reset, đến gần người gọi, thiếu một kênh, hết hạn, confidence thấp, xung đột và STOP bằng lời nói. Giao diện vẫn mở sau demo, robot giữ STOP. `ffmpeg` ghi trực tiếp các frame Qt; không cần quyền quay màn hình.

File tạo ra: `demo_48s.mp4` (10 fps, không âm thanh), `dashboard.png`, `states.jsonl` chứa pose và quyết định theo thời gian. Video minh họa lệnh/cử chỉ mô phỏng, không chứng minh khả năng nhận giọng nói hoặc webcam thật.

## Kiểm thử

```bash
source /opt/ros/humble/setup.bash
source install/local_setup.bash
colcon test --packages-select hri_multimodal --event-handlers console_direct+
colcon test-result --verbose
python3 src/hri_multimodal/test/check_runtime.py
python3 src/hri_multimodal/test/check_gazebo_runtime.py
```

Unit test kiểm tra bảng quyết định, chuẩn hóa tiếng Việt, confidence lỗi, snapshot nguyên tử, hết hạn và reset. Script runtime khởi động controller + simulator thật trong ROS domain 67, kiểm tra DDS/topic/service, chuyển động, đến người gọi, STOP và watchdog khi kill controller. Kết quả ghi vào `artifacts/hri_multimodal/runtime_validation.json` và log cùng tên. Dừng demo khác trên domain 67 trước khi chạy script.

| # | Lời nói | Cử chỉ | Confidence lời/cử chỉ | Kết quả mong đợi |
|---|---|---|---|---|
| 1 | Move forward | Thumb Up | .95/.95 | forward, agreement |
| 2 | Come here | Wave | .95/.95 | come, agreement |
| 3 | Move forward | Open Palm | .99/.01 | stop, stop_priority |
| 4 | Stop | Thumb Up | .01/.99 | stop, stop_priority |
| 5 | Move forward | thiếu | .95/0 | forward, voice_only |
| 6 | thiếu | Thumb Up | 0/.95 | forward, gesture_only |
| 7 | Move forward | Wave | .95/.95 | stop, conflict |
| 8 | Move forward | Thumb Up | .2/.3 | idle |
| 9 | thiếu | thiếu | 0/0 | idle |
| 10 | dance | Fist | 1/1 | idle |
| 11 | Move forward | Thumb Up | NaN/1 | stop, invalid_confidence |
| 12 | Lệnh tiến sau STOP | Thumb Up | .95/.95 | tiếp tục stop, cần reset |

Script Gazebo tự mở server headless trong domain 72 / partition riêng, inject nhãn cử chỉ và heartbeat camera để kiểm tra physics, so sánh odometry với pose ground truth và xác nhận các trường hợp dừng. File kết quả: `artifacts/hri_multimodal/gazebo_validation/runtime.json`. Đây không phải thử nhận dạng webcam.

Replay qua mô hình MediaPipe thật bằng một video webcam đã ghi:

```bash
.venv-gesture/bin/python src/hri_multimodal/test/check_camera_replay.py \
  --video artifacts/gesture_runs/20261027_075814/webcam_gestures.mp4
```

Script lấy 480 dòng ảnh trên để bỏ status panel của bản ghi lab cũ, chạy model và bộ lọc thời gian; phần Wave được kiểm tra bằng dịch ngang ảnh Open Palm thật. Kết quả ở `camera_replay.json`, không thay cho thử ba cử chỉ trực tiếp.

## Microphone thật (tùy chọn, offline)

Adapter dùng [Vosk](https://alphacephei.com/vosk/install) và [mẫu tiếng Anh nhỏ chính thức](https://alphacephei.com/vosk/models). Mô hình tiếng Anh phù hợp ba câu tiếng Anh của đề; các câu tiếng Việt vẫn dùng được ở giao diện văn bản.

```bash
cd /home/linh/ros2_ws
bash src/hri_multimodal/scripts/setup_voice.bash
source /opt/ros/humble/setup.bash
source install/local_setup.bash
export ROS_DOMAIN_ID=66 ROS_LOCALHOST_ONLY=1
./run_hri_voice.bash
```

Mở dashboard trong terminal khác, reset STOP nếu cần, rồi nói `Move forward`, `Come here`, `Stop`. Cử chỉ từ GUI còn hiệu lực vẫn tham gia fusion; để `None` và gửi nếu muốn kiểm tra riêng tiếng nói. Node công bố confidence thấp nhất của các từ từ Vosk; bản nhận dạng tạm thời `Stop` được phát ngay để dừng sớm. Không dùng grammar ép câu không biết thành lệnh.

Chọn micro bằng `./run_hri_voice.bash -p device:=N`. Liệt kê thiết bị:

```bash
LD_LIBRARY_PATH="$PWD/.hri-runtime/usr/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH):${LD_LIBRARY_PATH:-}" \
  .venv-hri/bin/python -m sounddevice
```

Setup tải mô hình, tạo `.venv-hri` và giải nén `libportaudio2` vào `.hri-runtime` nếu hệ thống chưa có, không dùng sudo. Kiểm tra microphone vật lý cần thực hiện riêng bằng giọng nói của người dùng.

## Xử lý lỗi

- `Package hri_multimodal not found`: build riêng package rồi source `install/local_setup.bash`.
- Không nhận topic: kiểm tra tất cả terminal dùng cùng domain 66 và `ROS_LOCALHOST_ONLY=1`.
- Robot đứng yên sau Open Palm: bấm reset và gửi lệnh mới; đây là chốt STOP.
- Robot chỉ đi 3 giây: tín hiệu đã hết hạn; gửi lại hoặc đổi `input_ttl`.
- Qt không kết nối display: chạy trong terminal desktop; có thể chạy `gui:=false` để kiểm tra headless. Kiểm tra `DISPLAY` và PyQt5. Script chạy đã xóa các đường dẫn plugin GTK/Qt dễ xung đột từ Snap.
- Video không có: kiểm tra `ffmpeg`, thư mục ghi và log dashboard. `record_dir` dùng cùng `demo:=true`.

## Nguồn kỹ thuật

- [MediaPipe Gesture Recognizer Python](https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer/python): nhận dạng frame và hand landmarks.
- [Gazebo DiffDrive](https://gazebosim.org/api/gazebo/6/classignition_1_1gazebo_1_1systems_1_1DiffDrive.html): robot hai bánh và odometry.
- [ros_gz bridge](https://github.com/gazebosim/ros_gz/tree/humble/ros_gz_bridge): nối Gazebo Transport với ROS 2.
