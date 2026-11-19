import base64
import uuid
import time
import json
import os
import re
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
        elif '===FRAMEPACK_RU===' in prompt:
            matches=re.search(r'Временные метки РЕАЛЬНЫХ выбранных кадров в порядке просмотра:\s*([^\n]+)',prompt)
            stamps=re.findall(r'([0-9]+(?:[.,][0-9]+)?\s*с)\b',matches.group(1)) if matches else []
            time_lines='\n'.join(t+' — видимая поза, без доказанного движения камеры' for t in stamps)
            answer=('===FRAMEPACK_RU===\nПерсонаж сохраняет видимые особенности, меняет положение на выбранных кадрах.\n'
                    '===FRAMEPACK_EN===\nThe character keeps their appearance while observed poses differ between sampled frames.\n'
                    '===TIMELINE_RU===\n'+time_lines+'\nМежду кадрами действие неизвестно.')
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

    def test_video_analysis_completes_missing_fields_before_done(self):
        img='data:image/jpeg;base64,'+base64.b64encode(b'missing-video-test').decode()
        payload={'kind':'video','depth':'fast','target':'FramePack F1',
                 'images':[{'time':'0.5','data':img},{'time':'1.5','data':img}]}
        sections='\n'.join('==='+k+'===\n'+(('English description of a woman standing in the scene.' if k.endswith('_EN') else 'Женщина стоит в комнате в мягком освещении.') if not k.startswith('FRAMEPACK') and k!='TIMELINE_RU' else '') for k in app.FIELDS)
        repair=('===FRAMEPACK_RU===\nЖенщина меняет положение головы при сохранении позы.\n'
                '===FRAMEPACK_EN===\nThe woman changes her head orientation while holding her pose.\n'
                '===TIMELINE_RU===\n0.50 с: прямо. 1.50 с: голова повернута.\n')
        replies=iter(['Первый кадр: прямо, второй: поворот головы.',sections,repair])
        with patch.object(app,'_llama_request',side_effect=lambda *args,**kwargs: next(replies)) as mocked:
            req=urllib.request.Request(self.url+'/api/analyze',data=json.dumps(payload).encode(),
                                       headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=6) as resp:
                events=[json.loads(x) for x in resp.read().decode().splitlines() if x.strip()]
        self.assertEqual(events[-1]['event'],'done')
        self.assertTrue(all(events[-1]['data']['sections'].get(k) for k in app.VIDEO_FIELDS))
        self.assertEqual(mocked.call_count,3)
        self.assertEqual(events[-1]['data']['frame_times'],['0.5','1.5'])

    def test_video_repair_one_model_call_for_three_sections(self):
        sections={'framepack_ru':'','framepack_en':'','timeline_ru':''}
        answer=('===FRAMEPACK_RU===\nПерсонаж поворачивает голову на первом кадре.\n'
                '===FRAMEPACK_EN===\nThe character turns their head between observed frames.\n'
                '===TIMELINE_RU===\n0.50 с: фронтальная поза. 1.50 с: голова повёрнута.\n')
        with patch.object(app,'_llama_request',return_value=answer) as mock:
            flags=app.repair_video_fields(sections,'На первом кадре фронтально, на втором повернута голова.', ['0.5','1.5'])
        self.assertEqual(mock.call_count,1)
        self.assertTrue(all(sections.get(k) for k in app.VIDEO_FIELDS))
        self.assertIn('0.50 с, 1.50 с',mock.call_args.args[0])
        self.assertEqual(len(flags),3)

    def test_video_repair_preserves_existing_and_fills_only_empty(self):
        sections={'framepack_ru':'Существующий русский промпт.',
                  'framepack_en':'', 'timeline_ru':''}
        answer=('===FRAMEPACK_RU===\nНовый текст, который не должен заменить старый.\n'
                '===FRAMEPACK_EN===\nThe person slowly turns toward the camera.\n'
                '===TIMELINE_RU===\n1.00 с: персонаж стоит прямо.\n')
        with patch.object(app,'_llama_request',return_value=answer):
            app.repair_video_fields(sections,'Наблюдается поворот.', ['1.0'])
        self.assertEqual(sections['framepack_ru'],'Существующий русский промпт.')
        self.assertTrue(sections['framepack_en'])
        self.assertTrue(sections['timeline_ru'])

    def test_video_repair_endpoint_does_not_need_images(self):
        body={'kind':'video','sections':{'framepack_ru':'','framepack_en':'','timeline_ru':''},
              'source_analysis':'Первый кадр: персонаж прямо. Второй кадр: повернулся.',
              'frame_times':['0.5','2.5']}
        answer=('===FRAMEPACK_RU===\nПерсонаж поворачивается в кадре.\n'
                '===FRAMEPACK_EN===\nThe person turns in frame.\n'
                '===TIMELINE_RU===\n0.50 с: прямо. 2.50 с: повёрнут.\n')
        with patch.object(app,'_llama_request',return_value=answer) as mock:
            req=urllib.request.Request(self.url+'/api/video/repair',
                     data=json.dumps(body).encode(),method='POST',
                     headers={'Content-Type':'application/json','Origin':self.url})
            with urllib.request.urlopen(req,timeout=5) as resp: data=json.load(resp)
        self.assertEqual(mock.call_count,1)
        self.assertEqual(data['missing'],[])
        self.assertIn('The person turns',data['sections']['framepack_en'])

    def test_video_repair_endpoint_rejects_remote_origin(self):
        body={'kind':'video','sections':{},'source_analysis':'Описание'}
        req=urllib.request.Request(self.url+'/api/video/repair',
                 data=json.dumps(body).encode(),method='POST',
                 headers={'Content-Type':'application/json','Origin':'https://evil.example'})
        with self.assertRaises(urllib.error.HTTPError) as cm:urllib.request.urlopen(req,timeout=3)
        self.assertEqual(cm.exception.code,403)

    def test_video_repair_failure_does_not_fake_output(self):
        sections={'framepack_ru':'','framepack_en':'','timeline_ru':''}
        with patch.object(app,'_llama_request',return_value='Bad no headings English only'):
            messages=app.repair_video_fields(sections,'Текст описания.')
        self.assertFalse(any(sections.values()))
        self.assertTrue(messages)

    def test_import_and_repair_controls_exist(self):
        ui=(Path(__file__).resolve().parents[1]/'ui'/'index.html').read_text(encoding='utf-8')
        for name in ['repairVideo','importJson','importJsonFile']:
            self.assertIn('id="'+name+'"',ui)

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
        self.assertEqual(version, '0.8.0')

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

    def test_v06_motion_prompts_independent_of_long_synthesis(self):
        self.assertIn('===APPEARANCE_RU===', app.SYNTH_VIDEO)
        self.assertNotIn('===FRAMEPACK_RU===', app.SYNTH_VIDEO)
        self.assertNotIn('===TIMELINE_RU===', app.SYNTH_VIDEO)
        self.assertIn('ВОЗМОЖНЫЙ МОНТАЖ', app.VIDEO_FOCUS)
        self.assertIn('по текстовым наблюдениям', app.VIDEO_REPAIR_PROMPT)

    def test_v06_timeline_coverage_exact_sample_times(self):
        self.assertEqual(app.missing_timeline_times('0.50 с: поза. 1,25 сек: другой ракурс.', ['0.5','1.25']), [])
        self.assertEqual(app.missing_timeline_times('0.50 с: поза.', ['0.50','1.25']), ['1.25 с'])
        self.assertEqual(app.missing_timeline_times('Временные метки: 0.50 с, 1.25 с', ['0.5','1.25']), ['0.50 с','1.25 с'])
        self.assertEqual(app.missing_timeline_times('нет данных', []), [])
        self.assertEqual(app.missing_timeline_times('нет данных', ['неизвестно']), [])

    def test_v06_video_timestamp_order_is_required(self):
        image='data:image/jpeg;base64,'+base64.b64encode(b'time').decode()
        for times in [['2.0','1.0'],['1.0','1.0'],['not-known','2.0']]:
            payload={'kind':'video','depth':'fast', 'images':[{'time':t,'data':image} for t in times]}
            req=urllib.request.Request(self.url+'/api/analyze',data=json.dumps(payload).encode(),
                                       headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as cm:urllib.request.urlopen(req,timeout=3)
            self.assertEqual(cm.exception.code,400)

    def test_v06_adaptive_video_keeps_provenance_and_dedicated_pass(self):
        image='data:image/jpeg;base64,'+base64.b64encode(b'adaptive-video').decode()
        frames=[{'time':f'{n/2:.2f}','data':image} for n in range(8)]
        payload={'kind':'video','depth':'fast','target':'FramePack F1','sampling_mode':'adaptive', 'images':frames}
        self.mock.requests.clear()
        req=urllib.request.Request(self.url+'/api/analyze',data=json.dumps(payload).encode(),
                                   headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as res:
            events=[json.loads(line) for line in res.read().decode().splitlines() if line.strip()]
        self.assertEqual(events[-1]['event'],'done',events[-1])
        report=events[-1]['data']
        self.assertEqual(report['video_sampling'],'adaptive')
        self.assertEqual(report['frame_times'],[f'{n/2:.2f}' for n in range(8)])
        self.assertIn('промежуточные движения',report['temporal_limitations'])
        self.assertEqual(report['complete'],len(app.FIELDS),report['quality_flags'])
        self.assertEqual(len(self.mock.requests),4)
        self.assertIn('===FRAMEPACK_RU===',self.mock.requests[-1]['messages'][1]['content'][0]['text'])
        self.assertNotIn('===APPEARANCE_RU===',self.mock.requests[-1]['messages'][1]['content'][0]['text'])
        self.assertEqual(app.missing_timeline_times(report['sections']['timeline_ru'], report['frame_times']),[])

    def test_v06_timeline_warns_incomplete_without_fabrication(self):
        original={k:'' for k in app.VIDEO_FIELDS}
        result=('===FRAMEPACK_RU===\nПерсонаж стоит в кадре, камера неподвижна.\n'
                '===FRAMEPACK_EN===\nThe subject stands in a stationary shot.\n'
                '===TIMELINE_RU===\n0.50 с — персонаж стоит у стены.')
        with patch.object(app,'_llama_request',return_value=result):
            warnings=app.repair_video_fields(original,'На первом кадре персонаж у стены. ',['0.5','1.5'])
        self.assertIn('1.50 с', '\n'.join(warnings))
        self.assertIn('0.50 с',original['timeline_ru'])
        self.assertNotIn('1.50 с',original['timeline_ru'])

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


class MotionDirectorV07Tests(unittest.TestCase):
    def base_project(self):
        return {'style':'anime','camera':'locked','pace':'natural','duration':5,
                'rating':'standard','identity_ru':'Женщина с зелёными глазами и тёмными волосами.',
                'scene_ru':'Небольшая комната с тёплым светом.',
                'direction_ru':'Сохранять лицо и одежду неизменными.',
                'manual_en':'The adult character turns her head, raises one hand, and smiles naturally.',
                'beats':[{'start':0,'end':2,'action':'Поворачивает голову направо.'},
                         {'start':2,'end':5,'action':'Поднимает руку и улыбается.'}]}

    def test_18_plus_requires_adult_confirmation(self):
        d=self.base_project();d.update(rating='adult',adults_confirmed=False)
        with self.assertRaisesRegex(ValueError,'совершеннолетие'):app.validate_motion_project(d)
        d['adults_confirmed']=True
        self.assertEqual(app.validate_motion_project(d)['rating'],'adult')

    def test_beats_strict_non_overlapping(self):
        d=self.base_project();d['beats'][1]['start']=1.5
        with self.assertRaisesRegex(ValueError,'наложений'):app.validate_motion_project(d)
        d=self.base_project();d['beats'][1]['end']=6
        with self.assertRaises(ValueError):app.validate_motion_project(d)

    def test_reject_invalid_style_and_camera(self):
        d=self.base_project();d['style']='unknown'
        with self.assertRaises(ValueError):app.validate_motion_project(d)
        d=self.base_project();d['camera']='drone'
        with self.assertRaises(ValueError):app.validate_motion_project(d)

    def test_manual_english_does_not_call_qwen(self):
        d=self.base_project()
        with patch.object(app,'_llama_request',side_effect=AssertionError('Qwen must not run')):
            result=app.build_motion_director(d)
        self.assertTrue(result['manual_input'])
        self.assertIn('anime',result['motion_en'].lower())
        self.assertIn('0–2',result['shotlist_ru'])
        self.assertIn('контур',result['motion_ru'])

    def test_russian_english_llm_prompt_pair(self):
        d=self.base_project();d['manual_en']='';d['style']='realistic'
        answer='===MOTION_RU===\nЖенщина медленно поворачивает голову вправо, затем поднимает руку и улыбается.\n===MOTION_EN===\nThe woman turns her head right, then raises a hand and smiles.'
        with patch.object(app,'_llama_request',return_value=answer) as q:
            result=app.build_motion_director(d)
        self.assertFalse(result['manual_input'])
        self.assertIn('photographic realism',result['motion_en'])
        self.assertIn('вправо',result['motion_ru'])
        self.assertIn('0–2',q.call_args.args[0])

    def test_bad_russian_translation_is_rejected(self):
        d=self.base_project();d['manual_en']=''
        answer='===MOTION_RU===\nThe woman is standing.\n===MOTION_EN===\nShe moves her hand.'
        with patch.object(app,'_llama_request',return_value=answer):
            with self.assertRaisesRegex(ValueError,'пару RU/EN'):app.build_motion_director(d)

    def test_framepack_restricts_all_network_targets_to_loopback(self):
        for value in ['https://example.com:7860','http://192.168.1.1:7860','http://127.0.0.1:8765','http://localhost:8080','http://x@127.0.0.1:7860','http://127.0.0.1:7860/evil','http://127.0.0.1:7860?url=x']:
            with self.subTest(value=value),self.assertRaises(ValueError):app._framepack_origin(value)
        self.assertEqual(app._framepack_origin('http://localhost:7861'),'http://127.0.0.1:7861')

    def test_framepack_config_api_requires_matching_input_schema(self):
        import io
        good={'dependencies':[{'api_name':'process','inputs':list(range(13)),'outputs':list(range(6))}]}
        with patch.object(app.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(good).encode())):
            name,_=app._framepack_config('http://127.0.0.1:7860')
        self.assertEqual(name,'process')
        bad={'dependencies':[{'api_name':'process','inputs':[1,2,3],'outputs':[]}]}
        with patch.object(app.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(bad).encode())):
            with self.assertRaisesRegex(ValueError,'схема'):app._framepack_config('http://127.0.0.1:7860')

    def test_gradio_sse_generates_file_only_on_confirmed_result(self):
        import io
        result_url='http://127.0.0.1:7860/gradio_api/file=output.mp4'
        messages=[]
        sse=b'event: generating\ndata: [null,null,"stage",null,null,null]\n\nevent: complete\ndata: [{"url":"'+result_url.encode()+b'"}]\n\n'
        data={'url':'http://127.0.0.1:7860','prompt':'The character moves her arm.',
              'image':'data:image/jpeg;base64,'+base64.b64encode(b'fake-image-dummy'*10).decode(),
              'duration':5,'seed':31337,'teacache':False}
        with patch.object(app,'_framepack_config',return_value=('process',{})),\
             patch.object(app,'_framepack_upload',return_value='C:/tmp/source.jpg'),\
             patch.object(app,'_framepack_http_json',return_value={'event_id':'abc123'}),\
             patch.object(app.urllib.request,'urlopen',return_value=io.BytesIO(sse)),\
             patch.object(app,'_framepack_save_result',return_value='framepack_20261119_201010_1234abcd.mp4') as sav:
            app.framepack_render(data,lambda e,**kw:messages.append((e,kw)))
        self.assertTrue(any(e=='done' for e,_ in messages))
        self.assertEqual(sav.call_args.args[0],result_url)

    def test_framepack_no_video_means_error_not_fake_success(self):
        import io
        data={'url':'http://127.0.0.1:7860','prompt':'The woman walks slowly.',
              'image':'data:image/jpeg;base64,'+base64.b64encode(b'fake-image-dummy'*10).decode(), 'duration':5}
        with patch.object(app,'_framepack_config',return_value=('process',{})),\
             patch.object(app,'_framepack_upload',return_value='C:/tmp/source.jpg'),\
             patch.object(app,'_framepack_http_json',return_value={'event_id':'abc123'}),\
             patch.object(app.urllib.request,'urlopen',return_value=io.BytesIO(b'event: complete\ndata: [null]\n\n')):
            with self.assertRaisesRegex(RuntimeError,'без итогового MP4'):app.framepack_render(data,lambda *args,**kw:None)

    def test_no_remote_video_result_url(self):
        payload={'url':'https://example.com/leak.mp4','path':''}
        self.assertEqual(app._framepack_result_file([payload],'http://127.0.0.1:7860'),'')
        self.assertIn('gradio_api/file=',app._framepack_result_file([{'path':'C:/outputs/a.mp4'}],'http://127.0.0.1:7860'))

    def test_backend_motion_route_requires_local_origin(self):
        d=self.base_project();data=json.dumps(d).encode('utf-8')
        url='http://127.0.0.1:'+str(self.app_server.server_address[1])+'/api/motion/build'
        bad=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json'},method='POST')
        with self.assertRaises(urllib.error.HTTPError) as exc:urllib.request.urlopen(bad,timeout=3)
        self.assertEqual(exc.exception.code,403)
        good=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:'+str(self.app_server.server_address[1])},method='POST')
        with urllib.request.urlopen(good,timeout=3) as response:
            result=json.load(response)
        self.assertTrue(result['motion_en'])

    @classmethod
    def setUpClass(cls):
        cls.app_server=server_for(app.Handler)

    @classmethod
    def tearDownClass(cls):
        cls.app_server.shutdown();cls.app_server.server_close()

class MockFramePackLiveProtocolTests(unittest.TestCase):
    def test_end_to_end_mock_gradio_without_external_requests(self):
        import tempfile
        from pathlib import Path
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        class FakeOfficialF1(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if self.path=='/config':
                    payload={'dependencies':[{'api_name':'process','inputs':list(range(13)),'outputs':list(range(6))}]}
                    content=json.dumps(payload).encode();self.send_response(200)
                    self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
                elif self.path=='/gradio_api/call/process/fake-event-123':
                    url=f'http://127.0.0.1:{self.server.server_port}/gradio_api/file=output.mp4'
                    content=('event: generating\ndata: [null,null,null,null,null,null]\n\n'
                             'event: complete\ndata: '+json.dumps([{'video':{'url':url,'path':'output.mp4'}},None,None,None,None,None])+'\n\n').encode()
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers();self.wfile.write(content)
                elif self.path=='/gradio_api/file=output.mp4':
                    content=b'FAKE MP4 BYTES FOR MOCK ONLY!'+b'0'*500
                    self.send_response(200);self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
                else:self.send_response(404);self.end_headers()
            def do_POST(self):
                length=int(self.headers['Content-Length']);body=self.rfile.read(length)
                if self.path=='/gradio_api/upload':
                    self.server.upload_received=('multipart/form-data' in self.headers['Content-Type'] and b'fake-image' in body)
                    content=b'["C:/tmp/source.jpg"]'
                elif self.path=='/gradio_api/call/process':
                    j=json.loads(body);self.server.args_received=j['data'];content=b'{"event_id":"fake-event-123"}'
                else:self.send_response(404);self.end_headers();return
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(content)
        server=ThreadingHTTPServer(('127.0.0.1',0),FakeOfficialF1)
        server.server_port=server.server_address[1]
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp,patch.object(app,'ROOT',Path(tmp)):
                url='http://127.0.0.1:'+str(server.server_port)
                src='data:image/jpeg;base64,'+base64.b64encode(b'fake-image'*20).decode()
                data={'url':url,'image':src,'prompt':'The woman slowly turns her head and raises one hand.',
                      'duration':5,'seed':2,'teacache':False}
                events=[]
                app.framepack_render(data,lambda ev,**kw:events.append((ev,kw)))
                result=events[-1]
                self.assertEqual(result[0],'done')
                output=Path(tmp)/'outputs'/result[1]['filename']
                self.assertTrue(output.exists())
                self.assertTrue(output.read_bytes().startswith(b'FAKE MP4'))
                self.assertTrue(server.upload_received)
                self.assertEqual(len(server.args_received),13)
                self.assertEqual(server.args_received[1],data['prompt'])
                self.assertEqual(server.args_received[4],5)
        finally:
            server.shutdown();server.server_close()

# v0.8 video-mode regression tests
class Video080(unittest.TestCase):
    @staticmethod
    def image(time):
        return {'time':time,'data':'data:image/jpeg;base64,'+base64.b64encode(b'fake').decode()}

    def test_video_only_report_fields(self):
        self.assertNotIn('positive_ru',app.VIDEO_REPORT_FIELDS)
        self.assertNotIn('anatomy_ru',app.VIDEO_REPORT_FIELDS)
        for name in ('participants_ru','setting_ru','process_ru','interactions_ru','rhythm_ru','adult_context_ru'):
            self.assertIn(name,app.VIDEO_REPORT_FIELDS)
        self.assertIn('===PROCESS_RU===',app.VIDEO_REPORT)
        self.assertIn('последовательности',app.VIDEO_OBSERVATION.lower())
        self.assertIn('РЕЖИМ 18+',app.VIDEO_OBSERVATION_ADULT)

    def test_temporal_trace_validation(self):
        good=[{'time':'0.1','change':1},{'time':'0.5','change':25.4}]
        value=app.validate_video_trace(good)
        self.assertEqual(value,[{'time':0.1,'change':1.0},{'time':0.5,'change':25.4}])
        self.assertIn('0.50с',app.temporal_evidence_text(value))
        for bad in ([{'time':1,'change':0},{'time':1,'change':1}],
                    [{'time':0,'change':256}], [{'time':-1,'change':0}],
                    [1], [{'time':0,'change':'not a number'}]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):app.validate_video_trace(bad)

    def test_photo_cannot_use_video_mode(self):
        self.assertRaisesRegex(ValueError,'1 до 8',app.validate_images,[self.image('0')]*9,'photo')
        self.assertEqual(len([self.image(str(n)) for n in range(20)]),20)
        app.validate_images([self.image(str(n)) for n in range(20)],'video')

    def test_video_parse(self):
        raw='===PARTICIPANTS_RU===\nДва человека.\n===PROCESS_RU===\nИзменения в 0.5 и 1.5 с.\n===UNCERTAINTY_RU===\nКонтакт закрыт.'
        fields=app.parse_video_sections(raw)
        self.assertEqual(fields['participants_ru'],'Два человека.')
        self.assertEqual(fields['process_ru'],'Изменения в 0.5 и 1.5 с.')
        self.assertEqual(fields['rhythm_ru'],'')

    def test_video_mode_cache_is_separate(self):
        images=[self.image('0.1'),self.image('0.2')]
        a=app._cache_key('video','standard','FramePack',images,'temporal','standard','same')
        b=app._cache_key('video','standard','FramePack',images,'temporal','adult','same')
        c=app._cache_key('video','standard','FramePack',images,'temporal','adult','different')
        self.assertEqual(len({a,b,c}),3)

    def test_actual_separate_video_path(self):
        report='\n'.join('==='+p.upper()+'===\n'+p+' — подтверждённые изменения в 0.100 и 0.900 с.' for p in app.VIDEO_REPORT_FIELDS)
        motion=('===FRAMEPACK_RU===\nУчастник изменяет положение головы между наблюдениями.\n'
                '===FRAMEPACK_EN===\nThe subject changes their head position between observed moments.\n'
                '===TIMELINE_RU===\n0.100 с — начало. 0.900 с — конец.')
        calls=[]
        def fake(prompt,images,max_tokens=2400,system_message=None):
            calls.append((prompt,len(images)))
            if '===FRAMEPACK_RU===' in prompt:return motion
            if '===PARTICIPANTS_RU===' in prompt:return report
            return '0.100 с — положение А. 0.900 с — положение Б. Видимая смена положения между моментами.'
        # Instantiate a real local server to cover validation and streaming.
        from http.server import ThreadingHTTPServer
        import threading
        srv=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        url=f'http://127.0.0.1:{srv.server_address[1]}'
        th=threading.Thread(target=srv.serve_forever,daemon=True);th.start()
        try:
            data={'kind':'video','video_mode':'adult','adults_confirmed':True,'depth':'fast',
                  'target':'FramePack F1','sampling_mode':'temporal',
                  'images':[self.image('0.100'),self.image('0.900')],
                  'temporal_trace':[{'time':0.1,'change':0.0},{'time':0.9,'change':24.3}]}
            with patch.object(app,'_llama_request',side_effect=fake):
                req=urllib.request.Request(url+'/api/analyze',data=json.dumps(data).encode(),
                        headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=5) as response:
                    events=[json.loads(line) for line in response.read().decode().splitlines() if line]
            self.assertEqual(events[-1]['event'],'done')
            result=events[-1]['data']
            self.assertEqual(result['video_mode'],'adult')
            self.assertEqual(result['video_engine'],'temporal-v0.8')
            self.assertIn('process_ru',result['sections'])
            self.assertNotIn('positive_ru',result['sections'])
            self.assertIn('framepack_en',result['sections'])
            self.assertIn('timeline_ru',result['sections'])
            self.assertEqual(len(calls),3)
            self.assertIn('РЕЖИМ 18+',calls[0][0]);self.assertEqual(calls[0][1],2)
            self.assertIn('===PROCESS_RU===',calls[1][0]);self.assertEqual(calls[1][1],0)
            self.assertIn('===FRAMEPACK_RU===',calls[2][0]);self.assertEqual(calls[2][1],0)
            # Reject misleading adult setting without consent.
            data['adults_confirmed']=False
            req=urllib.request.Request(url+'/api/analyze',data=json.dumps(data).encode(),
                    headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as exc: urllib.request.urlopen(req,timeout=5)
            self.assertEqual(exc.exception.code,400)
        finally:
            srv.shutdown();srv.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
