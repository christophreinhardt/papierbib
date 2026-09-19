"""Install only into a fresh temporary Calibre config, then test the real ZIP loader."""
import os
from pathlib import Path
import subprocess
import tempfile

from calibre.constants import get_version

root = Path(__file__).resolve().parent
archive = root / 'dist' / 'Papierbibliothek-0.6.11.zip'
with tempfile.TemporaryDirectory(prefix='papierbibliothek-calibre-') as config:
    env = dict(os.environ, CALIBRE_CONFIG_DIRECTORY=config, QT_QPA_PLATFORM='offscreen')
    subprocess.run(['calibre-customize', '-a', str(archive)], env=env, check=True)
    code = "from calibre.customize.ui import initialized_plugins; p=next(p for p in initialized_plugins() if p.name=='Papierbibliothek'); from calibre.gui2 import Application; app=Application([]); from calibre_plugins.papierbibliothek.calibre_plugin.action import PapierbibliothekAction; from calibre_plugins.papierbibliothek.ui.main import MainDialog; from calibre_plugins.papierbibliothek.ui.camera import CameraDialog; d=MainDialog(); d.show(); app.processEvents(); c=CameraDialog(devices=[],start_camera=False); assert 'Keine Kamera' in c.status.text(); print('Loaded action:', PapierbibliothekAction.name); print('Dialog:', d.windowTitle()); print('Camera dialog:',c.windowTitle()); c.close(); d.close(); print('ZIP plugin and both Qt dialogs verified successfully')"
    subprocess.run(['calibre-debug', '-c', code], env=env, check=True)
print('Calibre', get_version(), '- isolated plugin installation verified')
