"""Pure game validation. Never commands hardware or chooses an AI move."""
from dataclasses import dataclass, field

class InvalidMove(ValueError): pass

def winner(board,n):
    for r in range(n):
        for c in range(n):
            color=board[r*n+c]
            if not color: continue
            for dr,dc in [(0,1),(1,0),(1,1),(1,-1)]:
                if all(0<=r+dr*k<n and 0<=c+dc*k<n and board[(r+dr*k)*n+c+dc*k]==color for k in range(5)):
                    return color
    return 3 if all(board) else 0

@dataclass
class Game:
    n:int=8
    board:list=field(default_factory=list)
    phase:str='READY'
    human:int=1
    turn:int=1
    result:int=0
    last:tuple|None=None
    def __post_init__(self):
        if not self.board:self.board=[0]*(self.n*self.n)
    def start(self,human,observed,valid=True):
        if self.phase not in ('READY','FINISHED'):raise InvalidMove('게임이 이미 진행 중입니다.')
        if not valid:raise InvalidMove('판을 안정적으로 확인한 뒤 시작하세요.')
        if len(observed)!=self.n*self.n or any(observed):raise InvalidMove('판의 돌을 모두 치운 뒤 시작하세요.')
        self.board=[int(v) for v in observed];self.human=human;self.turn=1;self.result=0;self.last=None
        self.phase='HUMAN' if human==1 else 'ROBOT_WAIT'
    def validate(self,observed,offgrid=0,valid=True):
        if not valid:raise InvalidMove('관측 불확실: 마커, 가림, 돌 검출 상태를 확인하세요.')
        if len(observed)!=len(self.board) or any(v not in (0,1,2) for v in observed):raise InvalidMove('판 데이터가 올바르지 않습니다.')
        errors=[]
        if offgrid: errors.append('교차점 밖에 돌 후보가 있습니다. 교차점에 맞춰 놓으세요.')
        changed=[i for i,v in enumerate(self.board) if v and observed[i]!=v]
        added=[i for i,v in enumerate(self.board) if not v and observed[i]]
        if changed:errors.append('기존 돌이 이동·제거·변색되었습니다. 원래 상태로 복원하세요.')
        if len(added)>1:errors.append('돌은 한 번에 하나만 놓으세요.')
        if not added:errors.append('새로운 돌 한 개를 확인하지 못했습니다.')
        if any(observed[i]!=self.turn for i in added):errors.append('현재 차례의 돌 색이 아닙니다.')
        if errors:raise InvalidMove('\n'.join(errors))
        return added[0]
    def accept(self,observed,offgrid=0,valid=True):
        if self.phase not in ('HUMAN','ROBOT_WAIT'):raise InvalidMove('현재 상태에서는 착수를 확정할 수 없습니다.')
        idx=self.validate(observed,offgrid,valid)
        self.board=[int(v) for v in observed];self.last=divmod(idx,self.n);self.result=winner(self.board,self.n)  # int(): ROS int8 배열(numpy)이 GameState.winner 로 가면 controller 가 죽음
        if self.result:self.phase='FINISHED'
        else:
            self.turn=3-self.turn
            self.phase='HUMAN' if self.turn==self.human else 'ROBOT_WAIT'
        return self.last
