"""Run with calibre-debug run_standalone.py, without installing the plugin."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from calibre.gui2 import Application
from papierbibliothek.ui.main import MainDialog

app = Application([])
dialog = MainDialog(auto_open=True)
dialog.show()
sys.exit(app.exec())
