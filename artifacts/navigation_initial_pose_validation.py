import json, math, time
from pathlib import Path
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy, ReliabilityPolicy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from nav2_msgs.action import NavigateToPose
from irobot_create_msgs.action import Undock
from lifecycle_msgs.srv import GetState
from tf2_ros import Buffer, TransformListener
rclpy.init(); n=Node('validate_automatic_localization',parameter_overrides=[Parameter('use_sim_time',value=True)])
latest={}
for key,topic,kind in [('amcl','/amcl_pose',PoseWithCovarianceStamped),('gazebo','/sim_ground_truth_pose',Odometry)]:
    qos=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE) if key=='amcl' else qos_profile_sensor_data
    n.create_subscription(kind,topic,lambda m,key=key:latest.__setitem__(key,m),qos)
tf=Buffer();listener=TransformListener(tf,n)
def wait(future,limit=10):
    end=time.monotonic()+limit
    while not future.done():
        rclpy.spin_once(n,timeout_sec=.1)
        if time.monotonic()>end:raise RuntimeError('Timed out')
    return future.result()
report={'sent_initialpose':False,'lifecycle':{}}
try:
    for name in ['amcl','map_server','controller_server','planner_server','bt_navigator']:
        c=n.create_client(GetState,'/'+name+'/get_state')
        if not c.wait_for_service(timeout_sec=45):raise RuntimeError('No service for '+name)
        end=time.monotonic()+60
        while True:
            result=wait(c.call_async(GetState.Request()))
            if result.current_state.id==3:break
            rclpy.spin_once(n,timeout_sec=.2)
            if time.monotonic()>end:raise RuntimeError(name+' failed to activate')
        report['lifecycle'][name]=result.current_state.label
        print(name,result.current_state.label,flush=True)
    end=time.monotonic()+30
    while not all(k in latest for k in ['amcl','gazebo']) or not tf.can_transform('map','base_link',rclpy.time.Time()):
        rclpy.spin_once(n,timeout_sec=.1)
        if time.monotonic()>end:raise RuntimeError('Automatic pose or TF is missing')
    a=latest['amcl'].pose.pose.position;g=latest['gazebo'].pose.pose.position
    report['initial_amcl_xy']=[a.x,a.y];report['initial_gazebo_xy']=[g.x,g.y]
    report['initial_pose_error_m']=math.hypot(a.x-g.x,a.y-g.y)
    print('Automatically localized',report['initial_amcl_xy'],'Gazebo',report['initial_gazebo_xy'],flush=True)
    undock=ActionClient(n,Undock,'/undock')
    if not undock.wait_for_server(timeout_sec=15):raise RuntimeError('Undock unavailable')
    h=wait(undock.send_goal_async(Undock.Goal()))
    if not h.accepted:raise RuntimeError('Undock rejected')
    result=wait(h.get_result_async(),60);report['undock_status']=result.status
    if result.status!=4:raise RuntimeError('Undock failed')
    nav=ActionClient(n,NavigateToPose,'/navigate_to_pose')
    if not nav.wait_for_server(timeout_sec=15):raise RuntimeError('Navigation unavailable')
    goal=NavigateToPose.Goal();goal.pose.header.frame_id='map';goal.pose.header.stamp=n.get_clock().now().to_msg()
    goal.pose.pose.position.x=-2.;goal.pose.pose.position.y=0.;goal.pose.pose.orientation.w=1.
    h=wait(nav.send_goal_async(goal));print('Goal accepted:',h.accepted,flush=True)
    if not h.accepted:raise RuntimeError('Navigation rejected')
    try:result=wait(h.get_result_async(),120)
    except RuntimeError:
        wait(h.cancel_goal_async());raise
    report['navigation_goal']=[-2.,0.];report['navigation_status']=result.status
    g=latest['gazebo'].pose.pose.position;report['final_gazebo_xy']=[g.x,g.y]
    report['goal_error_gazebo_m']=math.hypot(g.x+2,g.y)
    report['passed']=result.status==4 and report['initial_pose_error_m']<.5
    print(json.dumps(report,indent=2),flush=True)
finally:
    Path('artifacts/navigation_initial_pose_results.json').write_text(json.dumps(report,indent=2))
    n.destroy_node();rclpy.shutdown()
if not report.get('passed'):raise SystemExit(1)
