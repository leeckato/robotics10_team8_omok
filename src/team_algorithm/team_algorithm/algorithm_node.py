"""
알고리즘 노드 (팀원 연결 규격 v0.1 '1. 알고리즘 담당')

  서비스 /algorithm/next_move  gomoku_interfaces/srv/NextMove
    입력: game_id, turn_id, request_id, int8[64] board (row*8+col, 0/1흑/2백), to_play
    출력: 세 식별자 그대로, success, row, col (0부터), error

로봇 동작, GUI 갱신, 턴 변경은 하지 않음 (게임 제어 담당).
"""
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from gomoku_interfaces.srv import NextMove

from team_algorithm.ai_core import AlphaZeroAI


class AlgorithmNode(Node):
    def __init__(self):
        super().__init__('team_algorithm')
        p = lambda name, default: self.declare_parameter(name, default).value   # noqa: E731
        self.time_warn = float(p('time_warn_sec', 10.0))
        self.ai = None
        self.load_error = ''
        try:
            self.ai = AlphaZeroAI(str(p('alphazero_path', '')),
                                  str(p('model_file', 'best_policy_8_8_5.model')),
                                  int(p('n_playout', 400)), float(p('c_puct', 5.0)))
            self.get_logger().info(f'[team_algorithm] AlphaZero 8x8 5목 모델 로드 ({self.ai.repo}), n_playout={self.ai.n_playout}')
        except Exception as e:                      # 모델이 없어도 노드는 떠서 실패 이유를 응답으로 돌려줌
            self.load_error = str(e)
            self.get_logger().error(f'[team_algorithm] 모델 로드 실패: {e}')
        self.create_service(NextMove, '/algorithm/next_move', self.next_move)
        self.get_logger().info('[team_algorithm] /algorithm/next_move 준비')

    def next_move(self, req, res):
        res.game_id, res.turn_id, res.request_id = req.game_id, req.turn_id, req.request_id
        try:
            if self.ai is None:
                raise RuntimeError('AI 모델 로드 실패: ' + self.load_error)
            row, col, dt = self.ai.next_move(list(req.board), int(req.to_play), req.game_id)
            res.success, res.row, res.col = True, int(row), int(col)
            color = '흑' if req.to_play == 1 else '백'
            log = self.get_logger().warn if dt > self.time_warn else self.get_logger().info
            log(f'[team_algorithm] turn {req.turn_id}: {color} -> ({row},{col})  {dt:.1f}s')
        except Exception as e:
            res.success, res.row, res.col, res.error = False, -1, -1, str(e)
            self.get_logger().error(f'[team_algorithm] turn {req.turn_id} 실패: {e}')
        return res


def main(args=None):
    rclpy.init(args=args)
    node = AlgorithmNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
