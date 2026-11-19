import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import updater


class UpdaterTests(unittest.TestCase):
    def test_missing_source_uses_official_repository(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(updater.config(Path(d))['manifest_url'], updater.DEFAULT_MANIFEST_URL)

    def test_blank_v02_source_uses_official_repository(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'update_config.json').write_text('{"manifest_url":""}', encoding='utf-8')
            self.assertEqual(updater.config(root)['manifest_url'], updater.DEFAULT_MANIFEST_URL)

    def test_bad_host(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'update_config.json').write_text(json.dumps({'manifest_url':'https://example.com/manifest.json'}))
            with self.assertRaises(updater.UpdateError):
                updater.check(root)

    def test_manifest_rejects_unlisted(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'update_config.json').write_text(json.dumps({'manifest_url':'https://raw.githubusercontent.com/me/pes/main/update-manifest.json'}))
            fake={'application':'prompt-extractor-studio','version':'0.6.1',
                  'files':[{'path':'../secrets.txt', 'size':0,'sha256':'0'*64}]}
            with patch.object(updater,'_get',return_value=json.dumps(fake).encode()):
                with self.assertRaises(updater.UpdateError):
                    updater.check(root)

    def test_current_version_does_not_offer_itself(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            url='https://raw.githubusercontent.com/me/pes/main/update-manifest.json'
            (root/'update_config.json').write_text(json.dumps({'manifest_url':url}),encoding='utf-8')
            entry={'application':'prompt-extractor-studio','version':updater.VERSION,
                   'files':[{'path':'app.py','size':3,'sha256':'0'*64}]}
            with patch.object(updater,'_get',return_value=json.dumps(entry).encode('utf-8')):
                result=updater.check(root)
            self.assertEqual(result['status'],'up_to_date')

    def test_verified_install_and_backup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'ui').mkdir()
            (root/'app.py').write_text('OLD',encoding='utf-8')
            (root/'qwen.gguf').write_text('DO NOT TOUCH')
            (root/'saved_results.json').write_text('DO NOT TOUCH')
            new=b'print("NEW")\n'
            url='https://raw.githubusercontent.com/me/pes/main/update-manifest.json'
            body={'application':'prompt-extractor-studio','version':'0.6.1',
                  'files':[{'path':'app.py','size':len(new),'sha256':hashlib.sha256(new).hexdigest()}]}
            (root/'update_config.json').write_text(json.dumps({'manifest_url':url}))
            def fake_get(path, limit):
                return json.dumps(body).encode() if path==url else new
            with patch.object(updater,'_get',side_effect=fake_get):
                info=updater.check(root)
                self.assertEqual(info['status'],'available')
                result=updater.install(root,info)
            self.assertEqual(result['version'],'0.6.1')
            self.assertEqual((root/'app.py').read_bytes(),new)
            self.assertEqual((Path(result['backup'])/'app.py').read_text(),'OLD')
            self.assertEqual((root/'qwen.gguf').read_text(),'DO NOT TOUCH')
            self.assertEqual((root/'saved_results.json').read_text(),'DO NOT TOUCH')

    def test_sha_error_keeps_old(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'app.py').write_text('OLD')
            url='https://raw.githubusercontent.com/me/pes/main/update-manifest.json'
            data=b'new but corrupted'
            body={'application':'prompt-extractor-studio','version':'0.6.1',
                  'files':[{'path':'app.py','size':len(data),'sha256':'0'*64}]}
            (root/'update_config.json').write_text(json.dumps({'manifest_url':url}))
            with patch.object(updater,'_get',side_effect=lambda path,limit: json.dumps(body).encode() if path==url else data):
                with self.assertRaises(updater.UpdateError):
                    updater.install(root,updater.check(root))
            self.assertEqual((root/'app.py').read_text(),'OLD')


if __name__=='__main__':unittest.main(verbosity=2)
