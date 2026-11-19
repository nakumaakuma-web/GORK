import base64
import uuid
import time
import json
import os
import sys
import threading
import unittest
import urllib.request
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class MockLlama(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200);self.end_headers();self.wfile.write(b'{"status":"ok"}')
        elif self.path == '/v1/models':
            self.send_response(200);self.end_headers();self.wfile.write(b'{"data":[{"id":"mock-qwen35"}]}')
        else:
            self.send_response(404);self.end_headers()

    def do_POST(self):
        size = int(self.headers['Content-Length'])
        request = json.loads(self.rfile.read(size))
        self.server.requests.append(request)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        contents = request['messages'][1]['content']
        prompt = contents[0]['text']
        if '===APPEARANCE_RU===' in prompt:
            answer = '\n'.join(f'==={k}===\n' + (('English prompt with accurate clothing and body position.' if k.endswith('_EN') else 'Русский промпт с точной одеждой и положением тела.') if k.startswith(('POSITIVE','NEGATIVE')) else 'Русское описание деталей лица и позы.') for k in app.FIELDS)
        else:
            answer = 'Описание: зелёные глаза, пряди, поза. Неясная сторона татуировки.'
        self.wfile.write(json.dumps({'choices':[{'message':{'content': answer}}]}).encode())


def server_for(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    server.requests=[]
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    return server


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock = server_for(MockLlama)
        app.LLAMA = 'http://127.0.0.1:' + str(cls.mock.server_address[1])
        cls.app = server_for(app.Handler)
        cls.url = 'http://127.0.0.1:' + str(cls.app.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown();cls.mock.shutdown()

    def test_sections(self):
        txt = '===POSITIVE_RU===\nА\n===POSITIVE_EN===\nB'
        parsed = app.parse_sections(txt)
        self.assertEqual(parsed['positive_ru'], 'А')
        self.assertEqual(parsed['positive_en'], 'B')

    def test_status_panel_live_elements(self):
        html=(Path(__file__).resolve().parents[1]/'ui'/'index.html').read_text(encoding='utf-8')
        for element in ('statusDetails','statusPhase','statusExplanation','statusFill','statusElapsed','statusHistory'):
            self.assertIn('id="'+element+'"', html)
        self.assertIn('min-height:62px',html)
        self.assertIn('font-size:17px',html)
        self.assertIn('pesStatusMove',html)

    def test_status_panel_uses_real_stage_events(self):
        source=(Path(__file__).resolve().parents[1]/'ui'/'ui.js').read_text(encoding='utf-8')
        self.assertIn("if(msg.event==='stage'){status(msg.message);stageUpdate(msg.message);}",source)
        self.assertIn('stageEnd(false,true)',source)
        self.assertIn('stageEnd(false);latest=msg.data',source)
        self.assertIn('stageEnd(true)',source)
        self.assertIn('stageTracker.startedStepAt',source)
        self.assertIn('Ответ появится после завершения прохода',source)

    def test_version_matches_updater(self):
        with urllib.request.urlopen(self.url + '/api/version') as response:
            version = json.load(response)['version']
        self.assertEqual(version, app.updater.VERSION)
        self.assertEqual(version, '0.5.1')

    def test_home_health(self):
        with urllib.request.urlopen(self.url) as r:
            self.assertIn('Prompt Extractor', r.read().decode())
        with urllib.request.urlopen(self.url + '/health') as r:
            self.assertTrue(json.load(r)['ready'])

    def test_update_check_returns_status(self):
        with patch.object(app.updater, 'check', return_value={'status':'up_to_date','current':'0.4.0','remote':'0.4.0'}):
            with urllib.request.urlopen(self.url + '/api/update/check') as r:
                state = json.load(r)
        self.assertEqual(state['status'], 'up_to_date')
        self.assertEqual(state['current'], '0.4.0')

    def test_update_requires_local_ui_origin(self):
        req = urllib.request.Request(self.url + '/api/update/install',
                                     data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(cm.exception.code, 403)

    def test_update_rejects_while_qwen_running(self):
        app._gpu_job_lock.acquire()
        try:
            req=urllib.request.Request(self.url+'/api/update/install',data=b'{}',
                    headers={'Content-Type':'application/json','Origin':self.url}, method='POST')
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req,timeout=3)
            self.assertEqual(cm.exception.code,409)
        finally:
            app._gpu_job_lock.release()

    def test_photo_pipeline(self):
        self.mock.requests.clear()
        image='data:image/jpeg;base64,'+base64.b64encode(b'test-image').decode()
        body=json.dumps({'kind':'photo','depth':'fast','target':'CyberIllustrious V4','images':[{'time':'','data':image}]}).encode()
        req=urllib.request.Request(self.url+'/api/analyze',data=body,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r:
            text=r.read().decode()
        events=[json.loads(x) for x in text.splitlines() if x.strip()]
        self.assertEqual(events[-1]['event'],'done')
        self.assertEqual(events[-1]['data']['sections']['positive_ru'], 'Русский промпт с точной одеждой и положением тела.')
        self.assertEqual(events[-1]['data']['complete'], len(app.FIELDS))
        self.assertEqual(len(self.mock.requests),2)
        self.assertEqual(self.mock.requests[0]['model'],'mock-qwen35')
        self.assertEqual(self.mock.requests[0]['messages'][1]['content'][1]['type'],'image_url')

    def test_memory_cache_avoids_repeat_qwen_requests(self):
        img='data:image/jpeg;base64,'+base64.b64encode(b'cache-case-05').decode()
        payload={'kind':'photo','depth':'fast','target':'Universal','images':[{'time':'','data':img}]}
        self.mock.requests.clear()
        out=[]
        for _ in range(2):
            data=json.dumps(payload).encode()
            req=urllib.request.Request(self.url+'/api/analyze',data=data,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=12) as r:
                out.append([json.loads(x) for x in r.read().decode().splitlines() if x.strip()])
        self.assertEqual(len(self.mock.requests),2) # analyze + synthesis on FIRST request only
        self.assertEqual(out[-1][-1]['event'],'done')
        self.assertTrue(out[-1][-1]['data']['cache_hit'])
        self.assertTrue(any(x['event']=='partial' for x in out[0]))

    def test_standard_photo_mode_three_calls(self):
        self.mock.requests.clear()
        img='data:image/jpeg;base64,'+base64.b64encode(b'standard-mode-photo').decode()
        data=json.dumps({'kind':'photo','depth':'standard','target':'Universal',
                         'images':[{'time':'','data':img}]}).encode()
        req=urllib.request.Request(self.url+'/api/analyze',data=data,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=12) as r:
            events=[json.loads(x) for x in r.read().decode().splitlines() if x.strip()]
        self.assertEqual(events[-1]['event'],'done')
        self.assertEqual(len(self.mock.requests),3)
        self.assertEqual(sum(x['event']=='partial' for x in events),2)

    def test_cancel_waits_until_current_model_call_ends(self):
        start=threading.Event()
        release=threading.Event()
        calls=[]
        returned=[]
        job=uuid.uuid4().hex
        image='data:image/jpeg;base64,'+base64.b64encode(b'cancel-test-'+job.encode()).decode()
        data=json.dumps({'kind':'photo','depth':'deep','job_id':job,'target':'Universal',
                        'images':[{'time':'','data':image}]}).encode()
        def fake_model(*args, **kwargs):
            calls.append(True)
            start.set()
            if not release.wait(5):
                raise RuntimeError('Timed out in test')
            return 'Текст визуального анализа.'
        def run():
            req=urllib.request.Request(self.url+'/api/analyze',data=data,
                                       headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=10) as resp:
                returned.extend(json.loads(x) for x in resp.read().decode().splitlines() if x.strip())
        with patch.object(app,'_llama_request',side_effect=fake_model):
            task=threading.Thread(target=run)
            task.start()
            try:
                self.assertTrue(start.wait(3))
                payload=json.dumps({'job_id':job}).encode()
                cancel=urllib.request.Request(self.url+'/api/analyze/cancel',data=payload,
                        headers={'Content-Type':'application/json','Origin':self.url})
                with urllib.request.urlopen(cancel,timeout=3) as resp:
                    outcome=json.load(resp)
                self.assertTrue(outcome['cancel_requested'])
            finally:
                release.set()
                task.join(timeout=5)
        self.assertFalse(task.is_alive())
        self.assertEqual(len(calls),1)
        self.assertTrue(any(x['event']=='cancelled' for x in returned))
        self.assertFalse(any(x['event']=='done' for x in returned))

    def test_cancel_requires_ui_origin(self):
        cancel=urllib.request.Request(self.url+'/api/analyze/cancel',
                 data=json.dumps({'job_id':uuid.uuid4().hex}).encode(),
                 headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(cancel,timeout=3)
        self.assertEqual(err.exception.code,403)

    def test_deep_photo_verifies_original_before_synthesis(self):
        image='data:image/jpeg;base64,'+base64.b64encode(b'photo').decode()
        self.mock.requests.clear()
        body=json.dumps({'kind':'photo','depth':'deep','target':'CyberIllustrious V4','images':[{'time':'','data':image}]}).encode()
        req=urllib.request.Request(self.url+'/api/analyze',data=body,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=15) as r:
            events=[json.loads(x) for x in r.read().decode().splitlines()]
        self.assertEqual(events[-1]['event'],'done')
        self.assertEqual(len(self.mock.requests),5)
        self.assertIn('ВТОРИЧНУЮ ВИЗУАЛЬНУ ПРОВЕРКУ',self.mock.requests[3]['messages'][1]['content'][0]['text'])
        self.assertEqual(self.mock.requests[3]['messages'][1]['content'][1]['type'],'image_url')
        self.assertTrue(events[-1]['data']['verified_analysis'])
        self.assertIn('quality_ru',events[-1]['data']['sections'])

    def test_language_guard_rejects_english_in_ru(self):
        self.assertFalse(app.prompt_language_matches('A woman wearing a beige dress with boots.', 'ru'))
        self.assertTrue(app.prompt_language_matches('Женщина в бежевом платье и сапогах.', 'ru'))
        self.assertFalse(app.prompt_language_matches('Платье бежевого цвета.', 'en'))
        self.assertTrue(app.prompt_language_matches('Beige dress, studio lighting.', 'en'))

    def test_repair_english_positive_ru(self):
        parts = {'positive_ru': 'A woman in a beige dress with gold jewelry.',
                 'positive_en': 'A woman in a beige dress with gold jewelry.',
                 'negative_ru': 'Искаженные пальцы и неправильная анатомия.',
                 'negative_en': 'Distorted fingers and incorrect anatomy.'}
        with patch.object(app, '_llama_request', return_value='Женщина в бежевом платье с золотыми украшениями.') as mocked:
            messages = app.ensure_prompt_languages(parts)
        self.assertEqual(mocked.call_count, 1)
        self.assertIn('бежевом платье', parts['positive_ru'])
        self.assertEqual(parts['positive_en'], 'A woman in a beige dress with gold jewelry.')
        self.assertTrue(any('POSITIVE_RU' in m for m in messages))

    def test_bad_retry_fails_closed(self):
        parts={'positive_ru': 'Still English even in the Russian field.'}
        with patch.object(app, '_llama_request', return_value='Still wrong English output.'):
            msgs=app.ensure_prompt_languages(parts)
        self.assertEqual(parts['positive_ru'], '')
        self.assertIn('неверный язык', msgs[0])

    def test_translation_error_does_not_abort_entire_analysis(self):
        parts={'positive_ru':'English material only, clearly no Russian.'}
        with patch.object(app, '_llama_request', side_effect=RuntimeError('test')):
            msgs=app.ensure_prompt_languages(parts)
        self.assertEqual(parts['positive_ru'], '')
        self.assertIn('не удалось', msgs[0])

    def test_detect_opposite_sides_ru_en(self):
        fields={'positive_ru':'Татуировка на левой стороне груди, правая рука поднята',
                'positive_en':'Tattoo on the right chest, right arm raised'}
        issues=app.audit_sections(fields,'photo')
        self.assertTrue(any('chest' in x for x in issues))
        self.assertFalse(any('arm (RU:' in x for x in issues))

    def test_cross_language_sides_selective_repair(self):
        fields={'positive_ru':'Женщина с татуировкой на левой стороне груди. Правая рука поднята.',
                'positive_en':'Woman with a tattoo on the right chest. Right arm raised.',
                'negative_ru':'Искажённые пальцы.',
                'negative_en':'Distorted fingers.'}
        self.assertTrue(any('chest' in item for item in app._pair_conflicts(fields['positive_ru'],fields['positive_en'])))
        with patch.object(app,'_llama_request',return_value='Woman with a tattoo on the left chest. Right arm raised.') as fake:
            notes=app.ensure_pair_consistency(fields)
        self.assertEqual(fake.call_count,1)
        self.assertIn('left chest',fields['positive_en'])
        self.assertFalse(app._pair_conflicts(fields['positive_ru'],fields['positive_en']))
        self.assertTrue(any('исправлено' in n for n in notes))

    def test_cross_language_failed_repair_keeps_old_english(self):
        fields={'positive_ru':'Татуировка на левой стороне груди.',
                'positive_en':'Tattoo on the right chest.'}
        with patch.object(app,'_llama_request',return_value='Tattoo on the right chest.') as fake:
            notes=app.ensure_pair_consistency(fields)
        self.assertEqual(fields['positive_en'],'Tattoo on the right chest.')
        self.assertTrue(notes)
        self.assertEqual(fake.call_count,1)

    def test_json_visual_passport_from_final_fields(self):
        passport=app.make_visual_passport({'appearance_ru':'Рыжие волосы',
                   'anatomy_ru':'Длинные руки', 'pose_ru':'Поворот корпуса',
                   'positive_ru':'Татуировка на левой руке.',
                   'uncertainty_ru':'Сторона зеркальна'},'photo')
        self.assertEqual(passport['source_kind'],'photo')
        self.assertEqual(passport['appearance'],'Рыжие волосы')
        self.assertEqual(passport['side_mentions_from_positive_ru']['arm'],['left'])
        self.assertEqual(passport['uncertainties'],'Сторона зеркальна')

    def test_quality_report_does_not_claim_certainty(self):
        self.assertIn('не гарантия',app.format_quality(['Тест'], 'deep', True))

    def test_video_pipeline(self):
        image='data:image/jpeg;base64,'+base64.b64encode(b'test-image').decode()
        images=[{'time':str(i),'data':image} for i in range(5)]
        body=json.dumps({'kind':'video','depth':'fast','target':'FramePack F1','images':images}).encode()
        req=urllib.request.Request(self.url+'/api/analyze',data=body,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r:
            events=[json.loads(x) for x in r.read().decode().splitlines()]
        self.assertEqual(events[-1]['data']['complete'],len(app.FIELDS))
        self.assertEqual(events[-1]['data']['kind'],'video')

    def test_reject_non_image(self):
        body=json.dumps({'kind':'photo','depth':'fast','images':[{'data':'http://example.com/image.png'}]}).encode()
        req=urllib.request.Request(self.url+'/api/analyze',data=body,headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as cm:urllib.request.urlopen(req,timeout=10)
        self.assertEqual(cm.exception.code,400)


if __name__=='__main__':unittest.main(verbosity=2)
