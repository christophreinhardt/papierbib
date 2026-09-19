"""Use Calibre's own Python/Qt. Offscreen, no live library or network."""
import os
from pathlib import Path
import sys
import unittest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))
from calibre.gui2 import Application
app = Application([])
suite = unittest.defaultTestLoader.discover(str(root / 'tests'))
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
