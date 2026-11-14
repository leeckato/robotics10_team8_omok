#!/usr/bin/env python3
"""
RH-P12-RN-A 그리퍼 제어 (공식 doosan-robot2 만 사용, 패치 불필요)

  원리: 두산 제어기의 DRL 함수 flange_serial_*() 로 Tool Flange RS-485 에
        Modbus RTU 프레임을 보내는 짧은 DRL 프로그램을 만들어서
        /dsr01/drl/drl_start 서비스로 실행합니다.

  사용:
    python3 gripper_drl.py open          # 열기   (Goal Position 0)
    python3 gripper_drl.py close         # 닫기   (Goal Position 700)
    python3 gripper_drl.py pos 350       # 원하는 위치 (0 ~ 700)
    python3 gripper_drl.py close --show  # 보낼 DRL 코드만 출력 (실행 안 함)
    python3 gripper_drl.py pos 630 --current 300   # 잡는 힘(목표 전류) 제한 후 이동
                                                   # (레지스터 275, gripper_cli.py 와 같은 방식)

  준비: bringup(mode:=real) 실행 중, 로봇 모드 자동(1), 펜던트 Tool Flange 출력 24 V
"""
import sys
import time

SLAVE_ID = 1
REG_TORQUE_ENABLE = 256     # 0x0100
REG_GOAL_POSITION = 282     # 0x011A  (2 레지스터, 32 bit)
REG_GOAL_CURRENT = 275      # 0x0113  (잡는 힘, gripper_cli.py 와 같은 레지스터)


def crc16(data):
    """Modbus RTU CRC16 (다항식 0xA001), 결과는 [하위 바이트, 상위 바이트]"""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return [crc & 0xFF, crc >> 8]


def frame(data):
    return list(data) + crc16(data)


def fc06_torque_on():
    """FC06 단일 레지스터 쓰기: Torque Enable = 1"""
    return frame([SLAVE_ID, 0x06, REG_TORQUE_ENABLE >> 8, REG_TORQUE_ENABLE & 0xFF, 0x00, 0x01])


def fc06_goal_current(cur):
    """FC06 단일 레지스터 쓰기: Goal Current (잡는 힘)"""
    cur = max(0, min(65535, int(cur)))
    return frame([SLAVE_ID, 0x06, REG_GOAL_CURRENT >> 8, REG_GOAL_CURRENT & 0xFF,
                  (cur >> 8) & 0xFF, cur & 0xFF])


def fc16_goal_position(pos):
    """FC16 다중 레지스터 쓰기: Goal Position (0 ~ 700)"""
    pos = max(0, min(700, int(pos)))
    return frame([SLAVE_ID, 0x10, REG_GOAL_POSITION >> 8, REG_GOAL_POSITION & 0xFF,
                  0x00, 0x02, 0x04, (pos >> 8) & 0xFF, pos & 0xFF, 0x00, 0x00])


def make_drl(pos, current=None, ramp_from=None, ramp_seconds=0.6, ramp_steps=6):
    """제어기에서 실행될 DRL 코드 (current 를 주면 목표 전류 먼저 설정)"""
    tq = fc06_torque_on()
    gp = fc16_goal_position(pos)
    position_lines=[]
    if ramp_from is not None:
        if not (0<=int(ramp_from)<=700 and 0<=int(pos)<=700):
            raise ValueError('Gripper ramp positions must be in 0..700')
        if not (2<=int(ramp_steps)<=20 and .1<=float(ramp_seconds)<=3):
            raise ValueError('Ramp needs 2..20 steps and 0.1..3 seconds')
        steps=int(ramp_steps);interval=float(ramp_seconds)/steps
        for i in range(1,steps+1):
            value=round(int(ramp_from)+(int(pos)-int(ramp_from))*i/steps)
            position_lines += [f'flange_serial_write(bytes({fc16_goal_position(value)}))',
                               f'wait({interval:.5f})',
                               f'flange_serial_read({min(.02,interval*.2):.5f})']
    else:
        position_lines=[f'flange_serial_write(bytes({gp}))','wait(0.1)','flange_serial_read(0.2)']
    cur_lines = []
    if current is not None:
        gc = fc06_goal_current(current)
        cur_lines = [
            f'flange_serial_write(bytes({gc}))',  # 잡는 힘(목표 전류)
            'wait(0.1)',
            'flange_serial_read(0.2)',
        ]
    return '\n'.join([
        'flange_serial_open(baudrate=57600, bytesize=DR_EIGHTBITS, parity=DR_PARITY_NONE, stopbits=DR_STOPBITS_ONE)',
        'wait(0.1)',
        f'flange_serial_write(bytes({tq}))',      # 토크 켜기
        'wait(0.1)',
        'flange_serial_read(0.2)',
    ] + cur_lines + position_lines + [
        'wait(1.0)',                              # 손가락이 움직이는 시간
        'flange_serial_close()',
    ])


def hexs(b):
    return ' '.join(f'{x:02X}' for x in b)


def main():
    argv = sys.argv[1:]
    current = None
    ramp_from=None;ramp_seconds=.6;ramp_steps=6
    ramp_values={}
    for option,converter in [('--ramp-from',int),('--ramp-seconds',float),('--ramp-steps',int)]:
        if option in argv:
            i=argv.index(option);ramp_values[option]=converter(argv[i+1]);del argv[i:i+2]
    ramp_from=ramp_values.get('--ramp-from')
    ramp_seconds=ramp_values.get('--ramp-seconds',.6);ramp_steps=ramp_values.get('--ramp-steps',6)
    if '--current' in argv:
        i = argv.index('--current')
        current = int(argv[i + 1])
        del argv[i:i + 2]
    args = [a for a in argv if not a.startswith('--')]
    show = '--show' in sys.argv
    virtual = '--virtual' in sys.argv
    if not args or args[0] not in ('open', 'close', 'pos') or (args[0] == 'pos' and len(args) < 2):
        print(__doc__)
        return
    pos = {'open': 0, 'close': 700}.get(args[0]) if args[0] != 'pos' else int(args[1])
    code = make_drl(pos, current, ramp_from, ramp_seconds, ramp_steps)
    print(f'Goal Position = {pos}' + (f', Goal Current = {current}' if current is not None else ''))
    print(f'  토크 프레임  : {hexs(fc06_torque_on())}')
    if current is not None:
        print(f'  전류 프레임  : {hexs(fc06_goal_current(current))}')
    print(f'  위치 프레임  : {hexs(fc16_goal_position(pos))}')
    if show:
        print('---- DRL ----\n' + code)
        return

    import rclpy
    from dsr_msgs2.srv import DrlStart, GetDrlState

    rclpy.init()
    node = rclpy.create_node('gripper_drl', namespace='dsr01')
    cli_start = node.create_client(DrlStart, 'drl/drl_start')
    cli_state = node.create_client(GetDrlState, 'drl/get_drl_state')
    if not cli_start.wait_for_service(timeout_sec=5.0):
        print('/dsr01/drl/drl_start 없음: bringup 이 실행 중인지 확인')
        node.destroy_node()
        rclpy.shutdown()
        raise SystemExit(1)

    req = DrlStart.Request()
    req.robot_system = 1 if virtual else 0      # 0 = 실제 로봇, 1 = 가상
    req.code = code
    fut = cli_start.call_async(req)
    rclpy.spin_until_future_complete(node, fut, timeout_sec=5.0)
    res = fut.result()
    print(f'drl_start success = {res.success if res else None}')
    if res is None or not res.success:
        node.destroy_node()
        rclpy.shutdown()
        raise SystemExit(1)

    # DRL 이 끝날 때까지 기다림 (drl_state 0 = 실행 중)
    if res and res.success and cli_state.wait_for_service(timeout_sec=1.0):
        t0 = time.time()
        while time.time() - t0 < 8.0:
            f = cli_state.call_async(GetDrlState.Request())
            rclpy.spin_until_future_complete(node, f, timeout_sec=1.0)
            st = f.result()
            if st is not None and st.drl_state != 0:
                break
            time.sleep(0.2)
        print('완료')
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()