"""Install the last uploaded camera configuration only when none exists."""
import json,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1]
dest=Path.home()/'.config/gomoku';config=dest/'marker_calibration.json'
if config.exists():
 print('Using existing camera calibration:',config)
else:
 source=root/'config/vision';data=json.loads((source/'marker_calibration.json').read_text())
 dest.mkdir(parents=True,exist_ok=True)
 ref=dest/'marker_calibration.empty.npz';shutil.copy2(source/ref.name,ref)
 data['reference_path']=str(ref.resolve());config.write_text(json.dumps(data,indent=2))
 print('Restored last uploaded camera calibration:',config)
