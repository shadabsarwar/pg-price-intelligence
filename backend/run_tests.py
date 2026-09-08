"""Run legacy fixture tests in a disposable, explicitly DEMO database."""
import os
import tempfile
import unittest

with tempfile.TemporaryDirectory(prefix='pg-tests-') as directory:
    os.environ['INTELLIGENCE_DB_PATH'] = os.path.join(directory, 'test.sqlite3')
    os.environ['INTELLIGENCE_DEMO'] = '1'
    suite = unittest.defaultTestLoader.discover('tests')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
