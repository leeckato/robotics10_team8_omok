# Qt Designer .ui 파일 (선택)

현재 GUI는 코드(`gui/widgets/*.py`)로 화면을 구성합니다.
Qt Designer로 화면을 그리고 싶다면 `.ui` 파일을 이 폴더에 저장하고 아래처럼 불러오면 됩니다.

```python
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile

f = QFile('gui/resources/ui/main_window.ui')
f.open(QFile.ReadOnly)
widget = QUiLoader().load(f)
```

또는 `pyside6-uic main_window.ui -o ui_main_window.py` 로 파이썬 코드로 변환해서 사용합니다.
