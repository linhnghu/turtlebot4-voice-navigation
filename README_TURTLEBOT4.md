# Bài thực hành TurtleBot 4 — ROS 2 Humble

Workspace: `/home/linh/ros2_ws`. Sử dụng TurtleBot 4 Lite và môi trường `maze`
có sẵn của TurtleBot 4, Gazebo Fortress, SLAM Toolbox và Nav2.
`maze` chạy từ tài nguyên đã cài, không cần tải mô hình Depot 82 MB từ Fuel.

## Cài đặt và build

Máy hiện tại đã có Ubuntu 22.04, ROS 2 Humble Desktop và Gazebo Fortress.
Các package dùng cho bài:

```bash
sudo apt install ros-humble-turtlebot4-simulator ros-humble-irobot-create-nodes \
  ros-humble-slam-toolbox ros-humble-navigation2 ros-humble-nav2-bringup \
  ros-humble-teleop-twist-keyboard
cd ~/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select turtlebot4_lab
```

Trong **mỗi terminal phụ**, chạy:

```bash
cd ~/ros2_ws
source turtlebot4_env.bash
```

File này đặt `ROS_DOMAIN_ID=49`, `ROS_LOCALHOST_ONLY=1`, nạp workspace,
sử dụng Fast DDS qua UDP trên loopback để tránh lỗi shared memory khi
khởi động lại mô phỏng,
sửa môi trường GTK/GIO từ VS Code Snap và tạo bản sao cục bộ của mô tả
Create 3 để chọn Ogre 2 cho sensor. Bản sao ở `.turtlebot4_compat/`;
không sửa file hệ thống. Trên máy này, Ogre 1 trả toàn bộ LiDAR bằng
`0.164 m`, dẫn đến bản đồ không có ô đã biết. Có thể tắt bản sửa bằng
`TURTLEBOT4_LAB_RENDERING_FIX=0` trước khi source môi trường.
File GUI của TurtleBot 4 được sao chép cùng overlay để camera Gazebo
khởi đầu ở trên cao, nhìn thấy robot và các tường thay vì sát mặt đất.

## Phần 1: Simulation

```bash
cd ~/ros2_ws
./run_turtlebot4.bash mode:=simulation
```

Gazebo và RViz mở cùng nhau. Nếu Gazebo bị pause, bấm Play.
Khi chuyển chế độ, dùng Ctrl+C ở terminal launch và chờ cửa sổ đóng.
Cũng có thể chạy `./stop_turtlebot4.bash` từ terminal khác.
Script dừng đợi các tiến trình của phiên mô phỏng kết thúc rồi mới trả về.
Nếu phiên cũ mất file PID nhưng Gazebo còn giữ khóa, script dừng sẽ tìm và
dọn tiến trình của workspace đang giữ khóa đó. `turtlebot4_session.py` quản lý
phiên chạy và các tiến trình con của Gazebo, kể cả tiến trình tự tách session.
RViz dùng frame `odom`; RobotModel và LaserScan `/scan` đã được bật.
Trong terminal phụ đã source môi trường:

```bash
ros2 run turtlebot4_lab check_topics.py
ros2 topic hz /scan
ros2 topic hz /odom
ros2 topic info /cmd_vel -v
```

Chạy các lệnh `hz` lần lượt, dùng Ctrl+C để kết thúc mỗi lần đo.
`check_topics.py` kiểm tra dữ liệu thực, khoảng LiDAR lớn hơn mức tối thiểu,
odometry, clock, TF và subscriber nhận Twist trên `/cmd_vel`.
Lệnh kiểm tra này không di chuyển robot; phải kiểm tra chuyển động riêng.

Robot được spawn tại dock. Trước khi điều khiển:

```bash
cd ~/ros2_ws
./run_teleop.bash
```

Script tự source cùng môi trường ROS domain 49, kiểm tra simulator đang chạy,
undock nếu robot còn ở dock, rồi mở teleop trên `/cmd_vel` với tốc độ `0.15 m/s`.
Đợi thông báo `Teleop ready` và hướng dẫn phím trước khi điều khiển.
Teleop: `i` tiến, `,` lùi, `j/l` quay trái/phải, `k` dừng.
Nhấp vào **terminal teleop**, giữ phím `i` để đi liên tục; nhấn `j/l` để quay.
Bản teleop hiện tại publish khi nhận phím, nên nhấn `i` một lần chỉ làm robot
di chuyển ngắn rồi controller dừng khi hết lệnh. Kiểm tra robot di chuyển
trong Gazebo và odometry thay đổi. Nhấn `k`, rồi Ctrl+C trước khi chuyển bước.

## Phần 2: SLAM và lưu bản đồ

Dừng launch simulation bằng Ctrl+C, chờ các cửa sổ đóng. Chạy:

```bash
./run_turtlebot4.bash mode:=mapping
```

Launch này chạy simulator, SLAM Toolbox đồng bộ và RViz với fixed frame `map`.
SLAM/AMCL khởi động sau simulator 8 giây; Nav2 khởi động sau 12 giây.
Giữ terminal launch này chạy; không nhấn Ctrl+C và không đóng Gazebo.
Mở **terminal thứ hai**, chạy:

```bash
cd ~/ros2_ws
./run_teleop.bash
```

Đợi `Teleop ready`, nhấp vào terminal thứ hai và giữ `i`; `j/l` quay, `k` dừng.
Đi chậm qua các lối đi, quan sát các khu vực chưa biết trên RViz; khảo sát
cả hai phía của tường dài giữa maze, các nhánh phía trên và phía dưới.
Quay lại khu vực đã đi qua để SLAM đóng vòng lặp. Tránh quay nhanh, va chạm,
hoặc tiếp tục di chuyển khi sensor/TF gặp lỗi.

```bash
ros2 run turtlebot4_lab check_topics.py --require-map
```

Khi đã khảo sát phần lớn diện tích và bản đồ không bị nhân đôi tường,
nhấn `k` để dừng, giữ SLAM đang chạy và lưu từ terminal phụ:

```bash
cd ~/ros2_ws
./save_map.bash
```

Kết quả: `maps/map.yaml`, `maps/map.pgm`. Map có độ phân giải từ cấu hình
SLAM Toolbox của TurtleBot 4 (mặc định `0.05 m/cell`). Script ghi đè bản đồ
cùng tên khi bạn lưu lại. Sau khi lưu thành công, đóng teleop và dùng Ctrl+C
ở terminal launch để dừng SLAM và simulator.
Ngưỡng free khi lưu đặt `0.196` để màu xám 205 trong PGM vẫn là vùng chưa biết
khi map server load lại bản đồ, tránh biến vùng chưa khảo sát thành vùng trống.

## Phần 3: Localization trên map đã lưu

```bash
./run_turtlebot4.bash mode:=localization map:=$HOME/ros2_ws/maps/map.yaml
```

Simulator khởi động lại cùng world và pose spawn. Chỉ AMCL + map server chạy
ở chế độ này; SLAM đã dừng. Mặc định launch tự khởi tạo AMCL tại
`(0, 0, yaw=0)` trên map để tạo TF và tránh Nav2 chờ initial pose.
So khớp LiDAR với map. Nếu vị trí chưa khớp, trên RViz chọn **2D Pose Estimate**,
đặt robot tại vị trí khởi đầu đúng trên map và kéo mũi tên theo hướng robot.
Nếu thay đổi pose spawn khi mapping, phải dùng lại đúng pose đó hoặc đặt
initial pose tương ứng. So khớp LiDAR với tường trên bản đồ và vị trí Gazebo.

Để thực hành tự đặt pose bằng RViz thay vì tự khởi tạo:

```bash
./run_turtlebot4.bash mode:=localization auto_initial_pose:=false
```

Khi chọn tùy chọn này, cần đặt **2D Pose Estimate** sau khi AMCL active.
Thông báo `AMCL cannot publish a pose ... Please set the initial pose` nghĩa là
AMCL đang chờ bước này. Nếu pose khởi đầu trên map khác mặc định, truyền
`initial_x:=... initial_y:=... initial_yaw:=...` (yaw tính bằng radian).

```bash
ros2 lifecycle get /amcl
ros2 lifecycle get /map_server
ros2 run turtlebot4_lab check_topics.py --require-map
ros2 run tf2_ros tf2_echo map base_link
```

AMCL và map server cần ở trạng thái `active`; TF cần có `map → odom → base_link`.
Dừng launch localization trước khi chuyển sang navigation.

## Phần 4: Nav2

```bash
./run_turtlebot4.bash mode:=navigation map:=$HOME/ros2_ws/maps/map.yaml
```

Chế độ này chạy cùng simulator, AMCL, map server, Nav2 và RViz.
AMCL tự khởi tạo pose như phần 3. Đợi panel RViz hiển thị Localization và
Navigation `active`, rồi kiểm tra LiDAR khớp map. Undock từ terminal phụ:

```bash
cd ~/ros2_ws
source turtlebot4_env.bash
ros2 action send_goal /undock irobot_create_msgs/action/Undock '{}'
```

Chọn **Nav2 Goal** trên RViz, nhấn ở vùng
trống đã khảo sát và kéo mũi tên để chọn hướng đến.

Thực hiện tối thiểu 3 goal ở các khu vực khác nhau: một goal gần điểm xuất
phát, một goal ở nhánh khác và một goal quay về vùng ban đầu. Chọn goal
trong vùng đã biết, cách tường/vật cản đủ xa. Sau khi gửi goal, dừng mọi
teleop; để Nav2 tự lập kế hoạch và điều khiển. Đợi goal thành công trước
khi gửi goal kế tiếp.

```bash
ros2 action list -t
ros2 lifecycle get /controller_server
ros2 lifecycle get /planner_server
ros2 topic echo /navigate_to_pose/_action/status
```

`status: 4` là SUCCEEDED; `5` CANCELED; `6` ABORTED.
Đối chiếu UUID và thời điểm với goal vừa gửi để tránh nhầm kết quả cũ.
Quan sát đường đi global/local trong RViz và chuyển động Gazebo.

Các dòng `Cleaning up`, `Deactivating`, `signal_handler(SIGINT/SIGTERM)` xuất hiện
khi phiên đang dừng. Lỗi `context is invalid` trong đoạn shutdown không xác định
nguyên nhân trước đó. Nếu Nav2 chờ TF `map`, kiểm tra log AMCL và initial pose
trước khi dừng launch. Giữ launch chạy trong lúc dùng RViz/terminal phụ.

## Minh chứng nộp bài

- Ảnh/video Gazebo có TurtleBot 4 và RViz có robot + LiDAR.
- Kết quả kiểm tra `/scan`, `/odom`, `/cmd_vel` và chuyển động robot.
- Video teleoperation khảo sát phần lớn môi trường, bản đồ hoàn chỉnh.
- `map.yaml` và `map.pgm` được lưu từ SLAM.
- Ảnh localization: LiDAR khớp map và robot khớp vị trí Gazebo.
- Video ít nhất 3 goal khác khu vực thành công, không điều khiển tay
  sau khi gửi goal, không va chạm.

Các log thử nghiệm nằm trong `artifacts/`. Bản đồ tạo khi kiểm tra kỹ thuật
chỉ là bản thử; cần hoàn tất khảo sát bằng teleoperation trước khi nộp bài.

## Teleop hiện phím nhưng robot không chạy

Giữ simulator/mapping chạy trong terminal thứ nhất và để Gazebo ở trạng thái
Play. Dùng `./run_teleop.bash` trong terminal thứ hai để mọi node dùng cùng
ROS domain và robot được undock. Giữ phím `i` khi terminal teleop đang focus.
Không nhấn phím trong cửa sổ RViz hoặc Gazebo khi dùng keyboard teleop này.

Trong terminal thứ ba đã source `turtlebot4_env.bash`, có thể kiểm tra:

```bash
ros2 run turtlebot4_lab check_topics.py --require-map
ros2 topic echo /cmd_vel
```

`/cmd_vel` phải nhận `linear.x: 0.15` khi bạn nhấn `i`. Nếu script báo thiếu
dữ liệu simulator, mở lại mapping; nếu báo undock thất bại, đọc thông báo
đó trước khi tiếp tục điều khiển.

## Tài liệu chính thức

- Simulator: https://github.com/turtlebot/turtlebot4_simulator/tree/humble
- Cài simulator: https://turtlebot.github.io/turtlebot4-user-manual/software/turtlebot4_simulator.html
- Navigation: https://turtlebot.github.io/turtlebot4-user-manual/tutorials/navigation.html
- Lỗi LiDAR Ogre 1 tương tự: https://github.com/iRobotEducation/create3_sim/issues/240

Hai URL trong đề có hậu tố `svg` thừa. Với Humble, dùng launch/package
Ignition; hướng dẫn Jazzy dùng tên `turtlebot4_gz_bringup` khác.
