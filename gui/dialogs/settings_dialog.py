"""자주 바꾸는 설정값 편집 -> config.yaml 저장"""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox, QLabel)

from utils.config import save_config


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle('설정')
        self.cfg = cfg
        form = QFormLayout(self)

        self.ed_source = QLineEdit(str(cfg['camera']['source']))
        self.sp_playout = QSpinBox(); self.sp_playout.setRange(50, 5000); self.sp_playout.setSingleStep(50)
        self.sp_playout.setValue(cfg['ai']['n_playout'])
        self.sp_stable = QSpinBox(); self.sp_stable.setRange(1, 60)
        self.sp_stable.setValue(cfg['vision']['stable_frames'])
        self.sp_patch = QDoubleSpinBox(); self.sp_patch.setRange(0.1, 0.5); self.sp_patch.setSingleStep(0.05)
        self.sp_patch.setValue(cfg['vision']['patch_ratio'])
        self.cb_hand = QComboBox(); self.cb_hand.addItems(['diff', 'mediapipe'])
        self.cb_hand.setCurrentText(cfg['vision']['hand']['method'])
        self.ck_human_first = QCheckBox('사람이 선공(흑)')
        self.ck_human_first.setChecked(cfg['game']['human_first'])
        self.ck_verify = QCheckBox('로봇이 놓은 돌을 카메라로 확인')
        self.ck_verify.setChecked(cfg['game']['verify_robot'])
        self.ck_logs = QCheckBox('매 수 사진/판 상태를 logs/ 에 저장')
        self.ck_logs.setChecked(cfg['game']['save_logs'])
        self.cb_driver = QComboBox(); self.cb_driver.addItems(['mock', 'custom'])
        self.cb_driver.setCurrentText(cfg['robot']['driver'])
        self.ed_port = QLineEdit(str(cfg['robot']['port']))

        form.addRow('카메라 (번호 또는 이미지 경로)', self.ed_source)
        form.addRow('AI 탐색 횟수 (n_playout)', self.sp_playout)
        form.addRow('인식 안정화 프레임', self.sp_stable)
        form.addRow('돌 판별 패치 비율', self.sp_patch)
        form.addRow('손 감지 방식', self.cb_hand)
        form.addRow('', self.ck_human_first)
        form.addRow('', self.ck_verify)
        form.addRow('', self.ck_logs)
        form.addRow('로봇 드라이버', self.cb_driver)
        form.addRow('로봇 포트', self.ed_port)
        form.addRow(QLabel('※ 판 크기·모델 등 나머지 값은 config.yaml 을 직접 수정하세요'))

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _save(self):
        c = self.cfg
        src = self.ed_source.text().strip()
        c['camera']['source'] = int(src) if src.isdigit() else src
        c['ai']['n_playout'] = self.sp_playout.value()
        c['vision']['stable_frames'] = self.sp_stable.value()
        c['vision']['patch_ratio'] = round(self.sp_patch.value(), 2)
        c['vision']['hand']['method'] = self.cb_hand.currentText()
        c['game']['human_first'] = self.ck_human_first.isChecked()
        c['game']['verify_robot'] = self.ck_verify.isChecked()
        c['game']['save_logs'] = self.ck_logs.isChecked()
        c['robot']['driver'] = self.cb_driver.currentText()
        c['robot']['port'] = self.ed_port.text().strip()
        save_config(c)
        self.accept()
