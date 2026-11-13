cmake_minimum_required(VERSION 3.8)
project(gomoku_interfaces)
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(action_msgs REQUIRED)
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/BoardObservation.msg" "msg/GameState.msg" "msg/HandState.msg" "msg/RobotStatus.msg"
  "srv/StartGame.srv" "srv/Inspect.srv" "srv/NextMove.srv" "srv/SetSimulation.srv"
  "action/PlaceStone.action" DEPENDENCIES builtin_interfaces action_msgs)
ament_export_dependencies(rosidl_default_runtime)
ament_package()
