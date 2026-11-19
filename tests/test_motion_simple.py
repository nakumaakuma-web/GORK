import base64
import hashlib
import json
import re
import sys
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app

GOOD=('===STATUS===\nREADY\n===OPTIONS_RU===\n\n===MOTION_RU===\n'
      'Персонаж поворачивает голову к камере и улыбается.\n'
      '===MOTION_EN===\nThe character turns toward the camera and smiles naturally.')
NEED=('===STATUS===\nNEEDS_ACTION\n===OPTIONS_RU===\n'
      'Персонаж медленно поворачивает голову к камере.\n'
      'Персонаж естественно моргает и смотрит в окно.\n'
      'Персонаж слегка меняет позу и улыбается.\n'
      '===MOTION_RU===\n\n===MOTION_EN===\n')

class MotionSimpleTests(unittest.TestCase):
    def data(self,**override):
        base={'source':'description','request_ru':'Девушка плавно поворачивается к камере и улыбается.',
              'duration':10,'style':'auto','camera':'locked','pace':'natural','loop':False,
              'rating':'standard','adults_confirmed':False,'video_sections':{}}
        return dict(base,**override)

    def test_reject_empty_description(self):
        with self.assertRaisesRegex(ValueError,'Напиши своими словами'):
            app.validate_framepack_order(self.data(request_ru=''))

    def test_reject_bad_duration_and_unconfirmed_adult(self):
        with self.assertRaisesRegex(ValueError,'5, 10 или 15'):
            app.validate_framepack_order(self.data(duration=11))
        with self.assertRaisesRegex(ValueError,'совершеннолетие'):
            app.validate_framepack_order(self.data(rating='adult'))

    def test_reject_missing_video_report(self):
        with self.assertRaisesRegex(ValueError,'Нет готового видеоанализа'):
            app.validate_framepack_order(self.data(source='video_analysis',request_ru='',video_sections={}))

    def test_needs_action_does_not_invent_motion(self):
        with patch.object(app,'_llama_request',return_value=NEED) as model:
            result=app.compose_framepack_order(self.data(request_ru='Девушка с каштановыми волосами на диване.'))
        self.assertEqual(result['status'],'needs_action')
        self.assertEqual(len(result['options_ru']),3)
        self.assertEqual(result['motion_en'],'')
        self.assertIn('только внешность',model.call_args.args[0])

    def test_one_prompt_translation_and_camera_loop(self):
        with patch.object(app,'_llama_request',return_value=GOOD) as model:
            result=app.compose_framepack_order(self.data(loop=True,duration=10))
        self.assertEqual(result['status'],'ready')
        self.assertIn('toward the camera',result['motion_en'])
        self.assertIn('initial pose',result['motion_en'])
        self.assertIn('locked-off camera',result['motion_en'].lower())
        self.assertIn('Рус',result['motion_ru']+'Рус')
        self.assertEqual(model.call_count,1)
        self.assertIn('ДЛИТЕЛЬНОСТЬ В FRAMEPACK: 10 сек',model.call_args.args[0])

    def test_video_analysis_mode_passes_process_without_photo_invention(self):
        section={'process_ru':'Человек поворачивает голову.', 'camera_ru':'Камера стоит на месте.',
                 'uncertainty_ru':'Движение рук не видно.'}
        with patch.object(app,'_llama_request',return_value=GOOD) as model:
            result=app.compose_framepack_order(self.data(source='video_analysis',request_ru='',video_sections=section))
        prompt=model.call_args.args[0]
        self.assertIn('Человек поворачивает голову',prompt)
        self.assertIn('Движение рук не видно',prompt)
        self.assertEqual(model.call_args.args[1],[])
        self.assertNotIn('image_data',result['project'])

    def test_start_photo_is_passed_to_qwen(self):
        image='data:image/jpeg;base64,'+base64.b64encode(b'test').decode()
        with patch.object(app,'_llama_request',return_value=GOOD) as model:
            app.compose_framepack_order(self.data(image_data=image))
        self.assertEqual(model.call_args.args[1],[{'time':'','data':image}])

    def test_bad_model_reply_rejected(self):
        with patch.object(app,'_llama_request',return_value='===STATUS===\nREADY\n===MOTION_EN===\nOnly English'):
            with self.assertRaisesRegex(ValueError,'пару RU/EN'):
                app.compose_framepack_order(self.data())

    def test_no_external_html_auto_insert_claim(self):
        base=Path(__file__).resolve().parents[1]
        html=(base/'ui'/'index.html').read_text(encoding='utf-8')
        js=(base/'ui'/'ui.js').read_text(encoding='utf-8')
        self.assertLess(html.index('id="pesTooltip"'),html.index('<script src="/ui.js"'))
        self.assertIn('id="quickBuild"',html)
        self.assertIn('id="quickFromVideo"',html)
        self.assertIn('value="10" selected',html)
        self.assertIn('<details class="motionAdvanced"',html)
        self.assertIn("'/api/motion/compose'",js)
        self.assertIn('e.target.closest?.(\'[data-help]\')',js)
        self.assertIn('Ctrl+V',js)

    def test_manifest_checksums_match_every_file(self):
        root=Path(__file__).resolve().parents[1]
        manifest=json.loads((root/'update-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['version'],'0.9.0')
        for entry in manifest['files']:
            p=root/entry['path']
            self.assertTrue(p.exists(),entry['path'])
            self.assertEqual(p.stat().st_size,entry['size'],entry['path'])
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),entry['sha256'],entry['path'])

    def test_compose_origin_enforced(self):
        # Localhost-only API can't be invoked from arbitrary sites.
        server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        Thread(target=server.serve_forever,daemon=True).start()
        try:
            url='http://127.0.0.1:'+str(server.server_address[1])+'/api/motion/compose'
            request=urllib.request.Request(url,data=json.dumps(self.data()).encode(),
                                           headers={'Content-Type':'application/json'},method='POST')
            with self.assertRaises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(request,timeout=3)
            self.assertEqual(exc.exception.code,403)
        finally:server.shutdown();server.server_close()

    def test_compose_endpoint_accepts_valid_request(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        Thread(target=server.serve_forever,daemon=True).start()
        try:
            url='http://127.0.0.1:'+str(server.server_address[1])
            request=urllib.request.Request(url+'/api/motion/compose',data=json.dumps(self.data()).encode(),
                                           headers={'Content-Type':'application/json','Origin':url},method='POST')
            with patch.object(app,'_llama_request',return_value=GOOD):
                with urllib.request.urlopen(request,timeout=5) as r:payload=json.load(r)
            self.assertEqual(payload['status'],'ready')
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
