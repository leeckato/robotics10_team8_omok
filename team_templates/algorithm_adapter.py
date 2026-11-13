"""Copy into your own ament_python package; fill call_existing_algorithm only."""
import rclpy
from rclpy.node import Node
from gomoku_interfaces.srv import NextMove

class AlgorithmAdapter(Node):
    def __init__(self):
        super().__init__('team_algorithm');self.create_service(NextMove,'/algorithm/next_move',self.next_move)
    def call_existing_algorithm(self,board,color):
        # Convert flat 64 cells to your AI's expected representation here.
        # Return (row, col), both zero based. Do not move the robot.
        raise NotImplementedError('Connect your existing AI here')
    def next_move(self,req,res):
        res.game_id=req.game_id;res.turn_id=req.turn_id;res.request_id=req.request_id
        try:
            row,col=self.call_existing_algorithm(list(req.board),req.to_play)
            if not (0<=row<8 and 0<=col<8) or req.board[row*8+col]:raise ValueError('Invalid AI move')
            res.row=int(row);res.col=int(col);res.success=True
        except Exception as e:res.success=False;res.error=str(e)
        return res

def main():
    rclpy.init();node=AlgorithmAdapter()
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:node.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()
