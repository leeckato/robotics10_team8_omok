"""돌 통에서 돌을 집어 목표 칸에 놓고 대기 위치로 돌아오기"""


class PickPlace:
    def __init__(self, arm, coords, z_safe=60.0, z_pick=10.0, z_place=10.0,
                 home=(150.0, 0.0, 120.0), supply=(200.0, -150.0)):
        self.arm, self.coords = arm, coords
        self.z_safe, self.z_pick, self.z_place = z_safe, z_pick, z_place
        self.home_pos, self.supply = tuple(home), tuple(supply)

    @classmethod
    def from_config(cls, cfg, arm, coords):
        r = cfg['robot']
        return cls(arm, coords, r['z_safe'], r['z_pick'], r['z_place'],
                   r['home'], r['stone_supply'])

    def go_home(self):
        self.arm.home(self.home_pos)

    def pick(self):
        x, y = self.supply
        self.arm.grip(False)
        self.arm.move_to(x, y, self.z_safe)
        self.arm.move_to(x, y, self.z_pick)
        self.arm.grip(True)
        self.arm.move_to(x, y, self.z_safe)

    def place(self, row, col, on_step=None):
        """(row, col) 칸에 돌 놓기. on_step(str) 로 진행 상황 알림"""
        step = on_step or (lambda s: None)
        x, y = self.coords.to_robot(row, col)
        step('돌 집는 중')
        self.pick()
        step(f'({row}, {col}) 로 이동')
        self.arm.move_to(x, y, self.z_safe)
        self.arm.move_to(x, y, self.z_place)
        step('돌 놓는 중')
        self.arm.grip(False)
        self.arm.move_to(x, y, self.z_safe)
        step('대기 위치로 복귀')
        self.go_home()
