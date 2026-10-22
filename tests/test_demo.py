import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('demo', ROOT / 'scripts/run_demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class DemoTests(unittest.TestCase):
    def test_end_to_end_outputs_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'output'
            result = demo.build(out)
            self.assertEqual(result['model_requests'], 0)
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(manifest['dataset_kind'], 'synthetic')
            for name, details in manifest['files'].items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), details['sha256'])
            analysis = json.loads((out / 'analysis.json').read_text())
            pair = next(p for p in analysis['pairs'] if set(p['heroes']) == {'赵云', '王昭君'})
            self.assertEqual((pair['appearances'], pair['wins']), (2, 1))
            self.assertEqual(len(json.loads((out / 'bp-check.json').read_text())['plans']), 2)
            self.assertIn('STEP 05', (out / 'index.html').read_text())

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'output'; out.mkdir()
            private = out / 'keep.txt'; private.write_text('keep me')
            with self.assertRaises(FileExistsError):
                demo.build(out)
            self.assertEqual(private.read_text(), 'keep me')
            self.assertEqual(len(list(out.iterdir())), 1)

    def test_renderer_escapes_markup_and_unsafe_links(self):
        rendered = demo.markdown('<script>alert(1)</script>\n\n[bad](javascript:alert)')
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('href="javascript:', rendered)


if __name__ == '__main__':
    unittest.main()
