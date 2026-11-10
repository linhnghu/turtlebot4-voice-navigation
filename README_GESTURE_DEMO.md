# Điều khiển TurtleBot 4 bằng cử chỉ tay

**Bài 07 — phân vùng bản đồ và điều hướng giọng nói:** [`Hướng dẫn chạy`](README_VOICE_NAV.md), ba vùng A/B/C, Whisper tiếng Việt offline và Nav2. Build/setup theo README rồi chạy `./run_voice_nav.bash`.

**Bài 01 — giọng nói + cử chỉ:** package ROS 2 riêng [`hri_multimodal`](src/hri_multimodal/README.md), có **Gazebo Fortress + nhận dạng webcam** và STOP ưu tiên. Chạy `./run_hri_gazebo.bash` sau khi build/setup. Bản 2D nhẹ: `./run_hri_demo.bash`.

**Non-verbal Human–Robot Interaction Using Hand Gesture Recognition**

Nhận diện cử chỉ từ **webcam laptop** bằng OpenCV và MediaPipe Gesture Recognizer,
điều khiển TurtleBot 4 Lite trong Gazebo Fortress qua ROS 2 Humble.
Robot hoạt động trong sân trống 20 × 20 m, có phản hồi odometry và bảo vệ LiDAR.

**Chọn hành vi → Thumbs Up xác nhận một lần → hạ tay → robot tự thực hiện đến hết.**
Không cần giữ ngón cái hoặc giữ tay trong webcam sau khi xác nhận.
Open Palm dừng; Closed Fist hủy và trở về trạng thái chờ.

[Hướng dẫn chi tiết](README_GESTURE_CONTROL.md) ·
[Báo cáo kiểm chứng](docs/GESTURE_VALIDATION.md) ·
[Kết quả controller trong Gazebo](docs/gesture_controller_validation.json)

## Các cử chỉ

| Cử chỉ | Nhãn `/detected_gesture` | Chức năng |
|---|---|---|
| Vẫy tay trái–phải | `Wave` | Chọn hành vi xoay trái–phải để chào |
| Giơ một ngón trỏ | `Pointing_Up` | Chọn tiến 0,12 m rồi lùi 0,12 m, đủ 4 chu kỳ |
| Giơ hai ngón chữ V | `Victory` | Chọn một vòng tròn, bán kính danh định 0,4 m |
| Giơ ngón cái | `Thumb_Up` | Xác nhận và bắt đầu hành vi đã chọn |
| Xòe bàn tay đứng yên | `Open_Palm` | Dừng ngay |
| Nắm tay | `Closed_Fist` | Hủy hành vi/lựa chọn, trở về chờ |

Giữ cử chỉ chọn/xác nhận khoảng 0,5–1 giây, đợi trạng thái `SELECTED` rồi
`RUNNING` trên cửa sổ webcam. Robot đứng yên khi mới chọn; động tác chào
cũng cần xác nhận. Khi hoàn tất, trạng thái là `COMPLETE`. Muốn chạy tiếp
phải chọn lại; giữ Thumbs Up không làm hành vi lặp vô hạn.

`Wave` được suy ra từ chuyển động ngang đổi chiều của landmarks bàn tay
đang được MediaPipe nhận là `Open_Palm`; năm cử chỉ tĩnh dùng classifier
có sẵn. Xem [cách vẫy tay và xử lý Open Palm](README_GESTURE_CONTROL.md#cử-chỉ-và-trình-tự-thao-tác).

## Yêu cầu

- Ubuntu 22.04, ROS 2 Humble Desktop, Gazebo Fortress và TurtleBot 4 Simulator.
- Python 3.10, `colcon`, webcam laptop hoặc USB hoạt động qua `/dev/video*`.
- Internet cho lần cài dependencies và tải model đầu tiên.

Sau khi đã cài ROS 2 Humble, cài các package cần thiết trên máy mới:

```bash
sudo apt update
sudo apt install ros-humble-turtlebot4-simulator ros-humble-irobot-create-nodes \
  python3-colcon-common-extensions python3-venv ffmpeg x11-utils
```

Dependency Python được cài riêng trong `.venv-gesture/`: MediaPipe `0.10.21`,
OpenCV contrib `4.11.0.86`, NumPy `1.26.4`. Model chính thức được tải vào
`.models/gesture_recognizer.task`. Không cần cài CUDA.

## Cài và chạy

Trên máy mới, clone vào workspace chưa tồn tại:

```bash
git clone https://github.com/linhnghu/turtlebot4-hand-gesture-control.git ~/ros2_ws
cd ~/ros2_ws
./setup_gesture.bash
```

Nếu đã có project trong `~/ros2_ws`, chỉ cần chạy `./setup_gesture.bash`
một lần; không clone chồng lên thư mục hiện tại.

Chạy demo:

```bash
cd ~/ros2_ws
./stop_turtlebot4.bash
./run_gesture_demo.bash
```

Giữ terminal launch chạy. Gazebo, TurtleBot 4, bridge, controller và cửa sổ
**TurtleBot 4 - Hand Gesture Webcam** được mở cùng một lệnh. Đợi controller
và cảm biến sẵn sàng, đưa một tay rõ nét vào webcam để chọn và xác nhận.
Không mở teleop/Nav2 trong phiên demo cử chỉ.

Có thể chọn camera khác bằng `./run_gesture_demo.bash camera_index:=2`.
Đóng ứng dụng khác đang chiếm webcam. Khi kết thúc, chạy:

```bash
./stop_turtlebot4.bash
```

## Quay video demo

Trước khi biểu diễn cử chỉ, mở terminal thứ hai:

```bash
cd ~/ros2_ws
./record_gesture_demo.py --duration 180
```

Script dùng ffmpeg ghi **Gazebo và webcam cạnh nhau** trên X11/XWayland.
Giữ cửa sổ mở, không minimize. Khi demo, không dùng bàn phím điều khiển robot.
Kịch bản: một ngón → Thumbs Up → hạ tay, đủ 4 chu kỳ; Victory → xác nhận →
hạ tay, đi hết vòng tròn; Wave → xác nhận, chào lại; sau đó thử Open Palm
và Closed Fist trong lúc robot đang chạy.

Mỗi lần chạy tạo `artifacts/gesture_runs/<thời điểm>/`; đường dẫn lần gần nhất
ở `artifacts/latest_gesture_run.txt`. Kết quả gồm:

- `demo_gazebo_gestures.mp4`: video hai cửa sổ khi dùng công cụ quay.
- `webcam_gestures.mp4`: ảnh webcam kèm landmarks, nhãn/score và trạng thái.
- `gestures.jsonl`, `behavior.jsonl`: kết quả nhận diện và chuyển trạng thái.

**Repo chưa có video biểu diễn đầy đủ sáu cử chỉ thật.** Cần người biểu diễn
trước webcam theo [kịch bản nộp bài](README_GESTURE_CONTROL.md#quay-video-nộp-bài).
Video YOLO ở `docs/demo/` thuộc bài trước.

## Luồng dữ liệu và bảo vệ

`OpenCV webcam → MediaPipe → /detected_gesture → robot_behavior_node → /cmd_vel`

- `/detected_gesture`: `std_msgs/msg/String`; `/cmd_vel`: `geometry_msgs/msg/Twist`.
- Bộ lọc score ≥ 0,65, cử chỉ chọn/xác nhận ổn định 0,3 giây và sự kiện theo
  lần đổi cử chỉ giúp hạn chế nhiễu/kích hoạt liên tục. Dừng/hủy không chờ bộ lọc này.
- Sau xác nhận, frame không có tay vẫn cho phép hành vi tiếp tục. Nếu camera
  lỗi hoặc mất hẳn luồng bản tin quá 0,8 giây, robot dừng.
- Kiểm tra odometry/LiDAR mới, khoảng cách vật cản tối thiểu 0,55 m, hazard,
  giới hạn khu vực 4 m và thời gian hành vi 70 giây. Giữ các bảo vệ Create 3.
- Tiến–lùi và xoay dùng odometry để xác định hoàn tất, có xử lý góc quấn ±π.

## Kiểm chứng

```bash
python3 -m unittest discover -s src/turtlebot4_gesture/test -v
```

Đã qua **18 kiểm thử logic**. Kiểm thử trong Gazebo dùng nhãn ROS tổng hợp:
chọn → Thumbs Up một lần → chỉ gửi `No_Hand` đến khi hoàn tất cả ba hành vi;
Open Palm/Closed Fist vẫn dừng/hủy sau khi đã hạ tay. Mất hẳn bản tin camera
cũng dừng robot. Webcam thật, model và công cụ ghi hai cửa sổ đã được chạy thử.
Các kết quả này chưa thay thế demo đủ sáu cử chỉ thật.
Xem [báo cáo](docs/GESTURE_VALIDATION.md) và [JSON](docs/gesture_controller_validation.json).

## Source và các bài trước

| Thành phần | Nội dung |
|---|---|
| [`src/turtlebot4_gesture/`](src/turtlebot4_gesture) | Hai ROS node, nhận Wave, máy trạng thái, launch, sân mô phỏng và kiểm thử |
| [`README_GESTURE_CONTROL.md`](README_GESTURE_CONTROL.md) | Cấu hình, thao tác, bảo vệ và xử lý lỗi chi tiết |
| [`src/turtlebot4_lab/`](src/turtlebot4_lab) | Simulation, SLAM, AMCL/Nav2 của bài trước |
| [`src/turtlebot4_vision_nav/`](src/turtlebot4_vision_nav) | Navigation qua ba goal và camera YOLO |
| [`README_TURTLEBOT4.md`](README_TURTLEBOT4.md) | Hướng dẫn SLAM và navigation |
| [`README_VISION_NAV.md`](README_VISION_NAV.md) | Hướng dẫn bài Nav2 + YOLO, video và kết quả riêng |
| [`maps/`](maps) | Map `maze` đã lưu |

Source các package được đưa trực tiếp vào repo. Không đưa `build/`, `install/`,
`log/`, virtualenv, weights hay video webcam tự sinh vào Git. Simulator, robot
description và controller upstream được cài qua package ROS chính thức.

## Tài liệu và license

- [MediaPipe Gesture Recognizer](https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer/python)
- [OpenCV VideoCapture](https://docs.opencv.org/4.x/dd/d43/tutorial_py_video_display.html)
- [TurtleBot 4 Simulation](https://turtlebot.github.io/turtlebot4-user-manual/software/simulation.html)

Source sử dụng [Apache-2.0](LICENSE). Gazebo world kế thừa ground/tường từ
TurtleBot 4 simulator, có ghi nguồn trong SDF. MediaPipe, model tải về và các
dependency giữ license tương ứng. Model người 3D và Ultralytics của bài trước
có nguồn/license riêng tại [ATTRIBUTION.md](src/turtlebot4_vision_nav/models/ATTRIBUTION.md).
