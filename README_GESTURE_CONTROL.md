# Giao tiếp phi ngôn ngữ và điều khiển TurtleBot 4 bằng cử chỉ tay

**Non-verbal Human–Robot Interaction Using Hand Gesture Recognition**

Webcam laptop → OpenCV → MediaPipe Gesture Recognizer → `/detected_gesture`
(`std_msgs/msg/String`) → `robot_behavior_node` → `/cmd_vel`
(`geometry_msgs/msg/Twist`) → TurtleBot 4 Lite trong Gazebo Fortress.

## Cài đặt và chạy

Dùng Ubuntu 22.04, ROS 2 Humble và simulator đã có trong workspace này.
Cần webcam thật có thể truy cập qua `/dev/video0`; đóng ứng dụng khác đang dùng camera.
Nếu máy mới chưa có môi trường Python/ghi màn hình:

```bash
sudo apt install python3-venv ffmpeg x11-utils
```

Cài lần đầu (cần Internet để tải dependencies và model chính thức):

```bash
cd ~/ros2_ws
./setup_gesture.bash
```

Script tạo `.venv-gesture` riêng, cài MediaPipe `0.10.21`, OpenCV contrib
`4.11.0.86`, NumPy `1.26.4`, tải `.models/gesture_recognizer.task` và build
package `turtlebot4_gesture`. Các lần sau chạy:

```bash
cd ~/ros2_ws
./stop_turtlebot4.bash
./run_gesture_demo.bash
```

Một lệnh mở sân trống 20 × 20 m trong Gazebo, spawn robot ở giữa sân,
khởi động controller/cảm biến, node nhận diện và cửa sổ **TurtleBot 4 - Hand
Gesture Webcam**. Robot bắt đầu ngoài dock; không tự chạy hành vi khi mở demo.
Chỉ dùng tay sau khi demo khởi động. Không mở teleop hoặc chạy Nav2 cùng phiên.

Nếu webcam khác chỉ số 0:

```bash
./run_gesture_demo.bash camera_index:=2
```

`/dev/video1` có thể chỉ là thiết bị metadata của camera 0, không phải camera thứ hai.
Đổi chỉ số theo camera thực tế. `show_window:=false` chỉ ẩn cửa sổ, vẫn nhận diện
và ghi camera; khi nộp video cần giữ cửa sổ hiển thị.

## Cử chỉ và trình tự thao tác

Đưa **một bàn tay** vào webcam, lòng bàn tay hướng về camera, đủ sáng. Giữ cử chỉ
chọn/xác nhận khoảng **0,5–1 giây**, đợi trạng thái trên cửa sổ chuyển đổi.

| Cử chỉ | Nhãn ROS | Hành vi |
|---|---|---|
| Vẫy tay trái–phải | `Wave` | Chọn chào: xoay trái → phải → trở về hướng ban đầu |
| Một ngón trỏ hướng lên | `Pointing_Up` | Chọn tiến 0,12 m rồi lùi 0,12 m, lặp **4 chu kỳ** |
| Hai ngón chữ V | `Victory` | Chọn một vòng tròn bán kính danh định 0,4 m |
| Ngón cái hướng lên | `Thumb_Up` | Xác nhận và bắt đầu hành vi đã chọn |
| Xòe tay đứng yên | `Open_Palm` | Dừng ngay, không chờ bộ lọc chọn lệnh |
| Nắm tay | `Closed_Fist` | Hủy hành vi và lựa chọn; về chờ |

**Chọn → xác nhận → thực hiện** áp dụng cho cả động tác chào. Sau khi chọn,
trạng thái hiện `SELECTED: ...; show Thumb Up`. Giơ ngón cái ổn định để bắt đầu,
sau đó **có thể hạ tay hoặc đưa tay ra khỏi webcam**. Robot tự thực hiện trọn
hành vi đã xác nhận, không cần giữ Thumbs Up. Hoàn thành hiện `COMPLETE`.
Trong lúc chạy, dùng Open Palm để dừng hoặc Closed Fist để hủy. Các cử chỉ
chọn hành vi khác không thay đổi hành vi đang chạy.

Open Palm dừng chuyển động và giữ lựa chọn chưa chạy, nếu có; muốn xóa cả
lựa chọn dùng Closed Fist. Hành vi đang chạy không được tiếp tục sau khi dừng:
cần chọn lại rồi xác nhận. Giữ Thumbs Up không lặp lại hành vi đã hoàn tất.

**Vẫy tay:** model có sẵn của MediaPipe không có nhãn Wave. Node dùng kết quả
`Open_Palm` và landmarks để nhận ít nhất ba nhịp dịch chuyển ngang đổi chiều
trong 1,6 giây, với biên độ theo kích thước bàn tay. Vẫy qua lại 2–3 lần cho
đến khi thấy `Wave`/`SELECTED: greeting`, rồi đổi sang Thumbs Up. Xòe tay
đứng yên vẫn là dừng. Khi bắt đầu vẫy trong lúc robot chạy, Open Palm ban đầu
sẽ dừng robot; chào chỉ chạy sau một lần xác nhận mới. Confidence hiển thị
cho Wave là score của lớp Open Palm nền, không phải xác suất riêng của Wave.

## Chống nhiễu và dừng an toàn

- Score tối thiểu 0,65 và cử chỉ chọn/xác nhận ổn định 0,3 giây.
- Mỗi cử chỉ ổn định tạo một sự kiện; giữ nguyên tay không kích hoạt liên tục.
- Nhiều tay không được dùng để chọn/xác nhận; Open Palm/Closed Fist vẫn có quyền dừng.
- Sau khi xác nhận, `No_Hand`, `Unknown` và `Multiple_Hands` vẫn là các frame
  camera đang hoạt động; robot tiếp tục hành vi đến hết. Không cần giữ tay.
- Trước khi xác nhận, lựa chọn chưa chạy hết hạn nếu không nhận cử chỉ hợp lệ
  trong 0,8 giây; chọn lại rồi xác nhận để bắt đầu.
- Không nhận bản tin frame camera nào quá 0,8 giây: gửi vận tốc 0 và xóa
  hành vi/lựa chọn. Lỗi camera gửi dừng ngay khi phát hiện. Hạ tay khỏi webcam
  khác với camera bị lỗi hoặc node nhận diện ngừng hoạt động.
- Vòng điều khiển 20 Hz dùng đồng hồ thực, tiếp tục kiểm tra timeout khi Gazebo pause.
- Chỉ chạy khi odometry mới trong 0,6 giây, LiDAR mới trong 0,8 giây,
  không có bumper/cliff/wheel-drop hazard, vật cản cách ít nhất 0,55 m và robot trong bán kính 4 m từ gốc odom.
- `BACKUP_LIMIT` là cảnh báo buffer lùi thấp, không được coi như bumper/cliff.
  Upstream `motion_control` vẫn chặn lùi khi buffer về 0. Mỗi đoạn lùi
  0,12 m nằm dưới mức buffer tối đa 0,15 m; luôn tiến trước khi lùi.
- Bật sẵn các bảo vệ Create 3; không tắt bumper/cliff reflex. Mỗi hành vi giới hạn 70 giây.
- Node camera/controller thoát sẽ kết thúc demo. Diff-drive upstream có timeout
  lệnh 0,5 giây nếu nguồn điều khiển ngừng phát.

Tiến–lùi dùng quãng đường odometry có dấu. Xoay/vòng tròn tích lũy góc odometry,
xử lý điểm quấn ±π; không chỉ gửi vận tốc rồi ngủ theo thời gian. Dừng là gửi
Twist bằng 0; thời gian dừng vật lý còn phụ thuộc chu kỳ ROS và gia tốc controller.
Sân trống và LiDAR giúp giới hạn va chạm trong bài mô phỏng; đây không phải
bộ lập kế hoạch né vật cản cho môi trường bất kỳ.

## Quay video nộp bài

Đặt Gazebo và webcam cùng dễ quan sát, phóng robot đủ lớn trong 3D View. Có thể
chỉnh camera bằng chuột trước khi demo, không dùng bàn phím điều khiển robot.
Ở terminal thứ hai, **trước khi diễn cử chỉ**, bắt đầu ghi 3 phút:

```bash
cd ~/ros2_ws
./record_gesture_demo.py --duration 180
```

Công cụ ghi hai cửa sổ Gazebo và webcam cạnh nhau bằng ffmpeg X11/XWayland.
Giữ cửa sổ mở, không minimize. Có thể Ctrl+C terminal **ghi hình** để kết thúc
sớm; thao tác này không điều khiển robot. Trên desktop thuần Wayland, dùng
công cụ quay màn hình của hệ điều hành nếu X11 capture không truy cập được cửa sổ.

Gợi ý kịch bản trong 2–3 phút:

1. Giơ một ngón tay; cho thấy robot đứng yên khi mới chọn.
2. Thumbs Up → hạ tay; robot vẫn thực hiện đủ 4 lượt tiến–lùi (khoảng 12–16 giây).
3. Victory → Thumbs Up → hạ tay; robot đi hết một vòng tròn (khoảng 22 giây).
4. Vẫy tay → Thumbs Up; robot xoay trái–phải chào lại.
5. Chọn/chạy vòng tròn lần nữa, xòe tay để chứng minh dừng ngay.
6. Chọn/chạy lại, nắm tay để chứng minh hủy và trở về chờ.
7. Chọn/chạy lại, đưa tay khỏi camera để chứng minh hành vi tiếp tục;
   sau đó xòe tay hoặc nắm tay để dừng/hủy.

Mỗi lần chạy tạo `artifacts/gesture_runs/<thời điểm>/`; đường dẫn gần nhất
ở `artifacts/latest_gesture_run.txt`:

- `demo_gazebo_gestures.mp4`: video hai cửa sổ, tạo khi chạy công cụ quay.
- `webcam_gestures.mp4`: camera, landmarks, nhãn/score và trạng thái; tự ghi
  trong demo, đóng file khi dừng. Đây không thay thế video có cả Gazebo.
- `gestures.jsonl`: nhãn/score/số tay và timestamp thật mỗi frame.
- `behavior.jsonl`: chuyển trạng thái và pose odometry.

Video webcam dùng tốc độ ghi danh định 20 fps; tốc độ suy luận thực tế có thể
thấp hơn, nên dùng video hai cửa sổ có thời gian thực để nộp bài.

Kết thúc và đóng file video:

```bash
./stop_turtlebot4.bash
```

## Kiểm tra và source

Xem [báo cáo kiểm chứng thực tế](docs/GESTURE_VALIDATION.md) để phân biệt
kết quả controller trong Gazebo với phần demo cử chỉ thật còn cần biểu diễn.

```bash
python3 -m unittest discover -s src/turtlebot4_gesture/test -v
```

Kiểm thử tích hợp controller trong Gazebo với **nhãn ROS tổng hợp**, phục vụ
kiểm tra phần chuyển động; không dùng làm video chứng minh nhận diện AI:

```bash
./run_gesture_demo.bash start_camera:=false
# Terminal khác:
source ~/ros2_ws/turtlebot4_env.bash
python3 ~/ros2_ws/src/turtlebot4_gesture/test/check_gazebo_behaviors.py
```

- [gesture_recognition_node.py](src/turtlebot4_gesture/scripts/gesture_recognition_node.py): webcam và MediaPipe Tasks API.
- [robot_behavior_node.py](src/turtlebot4_gesture/scripts/robot_behavior_node.py): ROS và bảo vệ cảm biến.
- [gesture_core.py](src/turtlebot4_gesture/scripts/gesture_core.py): bộ lọc theo thời gian và máy trạng thái hành vi.
- [gesture_demo.launch.py](src/turtlebot4_gesture/launch/gesture_demo.launch.py): simulator, bridge, controller và webcam.

Khi cần chẩn đoán, chỉ đọc topic ở terminal đã `source turtlebot4_env.bash`:
`ros2 topic echo /detected_gesture`, `ros2 topic echo /gesture_behavior/status`.
Không publish lệnh thủ công trong video cử chỉ. Nếu `BLOCKED`, kiểm tra
`/scan`, `/odom`, `/hazard_detection`; không bỏ bảo vệ để ép robot chạy.

## Tài liệu tham khảo

- [MediaPipe Gesture Recognizer Python](https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer/python)
- [OpenCV: đọc/hiển thị video](https://docs.opencv.org/4.x/dd/d43/tutorial_py_video_display.html)
- [TurtleBot 4 Simulation](https://turtlebot.github.io/turtlebot4-user-manual/software/simulation.html)

World `gesture_arena.sdf` giữ ground, tường bao, ánh sáng và physics từ world
`maze.sdf` của TurtleBot 4 simulator (Clearpath Robotics, Apache-2.0), bỏ các
vách mê cung. Model MediaPipe được tải từ Google và không đưa vào source Git.
