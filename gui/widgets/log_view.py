"""진행 로그 (시간 + 색상)"""
import html
from datetime import datetime

from PySide6.QtWidgets import QTextEdit

COLORS = {'info': '#222', 'warn': '#e65100', 'error': '#c62828'}


class LogView(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.document().setMaximumBlockCount(1000)

    def add(self, msg, level='info'):
        t = datetime.now().strftime('%H:%M:%S')
        color = COLORS.get(level, '#222')
        self.append(f'<span style="color:#888">[{t}]</span> '
                    f'<span style="color:{color}">{html.escape(msg)}</span>')
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
