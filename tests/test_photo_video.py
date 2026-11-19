"""v0.10 combined photo+video/text director contract tests."""
from pathlib import Path
from unittest.mock import patch
import base64, json, hashlib, sys, urllib.request, urllib.error, unittest
from http.server import ThreadingHTTPServer
from threading import Thread
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app

PHOTO='data:image/jpeg;base64,'+base64.b64encode(b'photo bytes').decode('ascii')
VIDEO='data:image/jpeg;base64,'+base64.b64encode(b'video bytes').decode('ascii')
GOOD=('===STATUS===\nREADY\n===OPTIONS_RU===\n\n'
      '===MOTION_RU===\nПерсонаж поднимает руку, плавно поворачивает голову.\n'
      '===MOTION_EN===\nThe character raises a hand and slowly turns the head.\n'
      '===COMPATIBILITY_RU===\nДвижение подстроено под исходную сидячую позу.\n')
REF=('===PROCESS_RU===\nЧеловек поворачивает голову.\n'
     '===RHYTHM_RU===\nМедленно.\n===CAMERA_RU===\nКамера стабильна.\n'
     '===TIMELINE_RU===\n0.2 с: взгляд прямо. 1.2 с: голова повёрнута.\n'
     '===INTERACTIONS_RU===\nВидимых контактов нет.\n'
     '===UNCERTAINTY_RU===\nНевозможно определить движение между кадрами.\n')

class PhotoToVideoTests(unittest.TestCase):
    def order(self,**kw):
        order={'source':'photo_video','image_data':PHOTO,'request_ru':'Повернуть голову и поднять руку.',
               'video_sections':{},'style':'auto','pace':'natural','camera':'locked',
               'duration':10,'loop':False,'rating':'standard','adults_confirmed':False}
        order.update(kw)
        return order

    def test_requires_canonical_image(self):
        with self.assertRaisesRegex(ValueError,'исходная фотография'):
            app.validate_framepack_order(self.order(image_data=''))

    def test_requires_motion_or_description(self):
        with self.assertRaisesRegex(ValueError,'видеоотчёт движения'):
            app.validate_framepack_order(self.order(request_ru='',video_sections={}))

    def test_image_and_text_suffice(self):
        with patch.object(app,'_llama_request',return_value=GOOD) as llama:
            data=app.compose_framepack_order(self.order())
        self.assertEqual(data['status'],'ready')
        self.assertIn('поворачивает',data['motion_ru'])
        self.assertIn('raises a hand',data['motion_en'])
        self.assertIn('сидячую',data['compatibility_ru'])
        self.assertEqual(len(llama.call_args.args[1]),1)
        self.assertEqual(llama.call_args.args[1][0]['data'],PHOTO)

    def test_video_reference_and_user_note_are_both_used(self):
        example={'process_ru':'Другой актёр встал со стула и повернулся.',
                 'rhythm_ru':'Плавно, без рывков.',
                 'timeline_ru':'0.2 сек поворот, 2.0 сек остановка.'}
        with patch.object(app,'_llama_request',return_value=GOOD) as llama:
            result=app.compose_framepack_order(self.order(request_ru='Сохранить моё лицо, поворот сделать медленнее.',video_sections=example))
        prompt=llama.call_args.args[0]
        self.assertIn('ВИДЕООТЧЁТ — только ОБРАЗЕЦ ДВИЖЕНИЯ',prompt)
        self.assertIn('ТЕКСТОВЫЙ ЗАКАЗ может уточнить',prompt)
        self.assertIn('Сохранить моё лицо',prompt)
        self.assertIn('Другой актёр',prompt)
        self.assertEqual(result['project']['source'],'photo_video')
        self.assertNotIn('image_data',result['project'])

    def test_video_only_is_allowed(self):
        with patch.object(app,'_llama_request',return_value=GOOD):
            result=app.compose_framepack_order(self.order(request_ru='',video_sections={'process_ru':'Персонаж плавно поворачивает голову.'}))
        self.assertEqual(result['status'],'ready')

    def test_text_only_without_action_offers_choices(self):
        reply='===STATUS===\nNEEDS_ACTION\n===OPTIONS_RU===\n1. Персонаж поворачивает голову.\n2. Персонаж улыбается.\n3. Персонаж машет рукой.\n===MOTION_RU===\n\n===MOTION_EN===\n'
        with patch.object(app,'_llama_request',return_value=reply):
            result=app.compose_framepack_order(self.order(request_ru='Женщина у окна.'))
        self.assertEqual(result['status'],'needs_action')
        self.assertEqual(result['motion_en'],'')
        self.assertEqual(len(result['options_ru']),3)

    def test_invalid_video_timestamp(self):
        frames=[{'time':'2.0','data':VIDEO},{'time':'1.0','data':VIDEO}]
        with self.assertRaisesRegex(ValueError,'по возрастанию'):
            app.analyze_motion_reference({'images':frames})

    def test_video_reference_uses_temporal_chunks_and_returns_motion(self):
        frames=[{'time':str(i+.2),'data':VIDEO} for i in range(9)]
        with patch.object(app,'_llama_request',side_effect=['0–3 с: корпус поворачивается.', '4–7 с: пауза.', '8 с: возврат.', REF]) as llama:
            result=app.analyze_motion_reference({'images':frames})
        self.assertEqual(llama.call_count,4)
        self.assertEqual([len(call.args[1]) for call in llama.call_args_list],[4,4,1,0])
        self.assertIn('поворачивает',result['sections']['process_ru'])
        self.assertEqual(len(result['frame_times']),9)
        self.assertEqual(result['kind'],'motion_reference')

    def test_failed_video_result_rejected(self):
        frames=[{'time':'0.0','data':VIDEO},{'time':'0.5','data':VIDEO}]
        with patch.object(app,'_llama_request',side_effect=['Нет движения','нет тегов']):
            with self.assertRaisesRegex(ValueError,'хронологию'):
                app.analyze_motion_reference({'images':frames})

    def test_cannot_send_reference_from_external_site(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        Thread(target=server.serve_forever,daemon=True).start()
        try:
            url='http://127.0.0.1:'+str(server.server_address[1])
            req=urllib.request.Request(url+'/api/motion/reference',data=b'{}',method='POST',headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as exc:urllib.request.urlopen(req,timeout=3)
            self.assertEqual(exc.exception.code,403)
        finally:server.shutdown();server.server_close()

    def test_three_mode_ui_exists(self):
        root=Path(__file__).resolve().parents[1]
        html=(root/'ui/index.html').read_text(encoding='utf-8')
        js=(root/'ui/ui.js').read_text(encoding='utf-8')
        for identity in ('modeCombine','p2vWorkspace','p2vPhotoFile','p2vVideoFile','p2vText',
                         'p2vImportVideo','p2vAnalyzeVideo','p2vBuild','p2vOutputRu','p2vOutputEn'):
            self.assertIn('id="'+identity+'"',html)
        self.assertIn("source:'photo_video'",js)
        self.assertIn("'/api/motion/reference'",js)
        self.assertEqual(html.count('id="sourceModes"'),1)

    def test_manifest_integrity(self):
        root=Path(__file__).resolve().parents[1]
        manifest=json.loads((root/'update-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['version'],'0.10.0')
        for item in manifest['files']:
            b=(root/item['path']).read_bytes()
            self.assertEqual(len(b),item['size'],item['path'])
            self.assertEqual(hashlib.sha256(b).hexdigest(),item['sha256'],item['path'])

if __name__=='__main__':unittest.main()
