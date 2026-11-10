cmake_minimum_required(VERSION 3.8)
project(turtlebot4_gesture)
find_package(ament_cmake REQUIRED)
install(DIRECTORY launch worlds DESTINATION share/${PROJECT_NAME})
install(PROGRAMS scripts/gesture_recognition_node.py scripts/robot_behavior_node.py
  DESTINATION lib/${PROJECT_NAME})
install(FILES scripts/gesture_core.py DESTINATION lib/${PROJECT_NAME})
ament_package()
