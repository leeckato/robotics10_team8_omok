from rclpy.qos import QoSProfile,DurabilityPolicy,ReliabilityPolicy

def state_qos():
    return QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE)
