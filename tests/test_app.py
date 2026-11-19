import base64
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
            answer = '\n'.join(f'==={k}===\nValue {k}' for k in app.FIELDS)
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

    def test_home_health(self):
        with urllib.request.urlopen(self.url) as r:
            self.assertIn('Prompt Extractor', r.read().decode())
        with urllib.request.urlopen(self.url + '/health') as r:
            self.assertTrue(json.load(r)['ready'])

    def test_update_check_returns_status(self):
        with patch.object(app.updater, 'check', return_value={'status':'up_to_date','current':'0.3.0','remote':'0.3.0'}):
            with urllib.request.urlopen(self.url + '/api/update/check') as r:
                state = json.load(r)
        self.assertEqual(state['status'], 'up_to_date')
        self.assertEqual(state['current'], '0.3.0')

    def test_update_requires_local_ui_origin(self):
        req = urllib.request.Request(self.url + '/api/update/install',
                                     data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(cm.exception.code, 403)

    def test_photo_pipeline(self):
        image='data:image/jpeg;base64,'+base64.b64encode(b'test-image').decode()
        body=json.dumps({'kind':'photo','depth':'fast','target':'CyberIllustrious V4','images':[{'time':'','data':image}]}).encode()
        req=urllib.request.Request(self.url+'/api/analyze',data=body,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r:
            text=r.read().decode()
        events=[json.loads(x) for x in text.splitlines() if x.strip()]
        self.assertEqual(events[-1]['event'],'done')
        self.assertEqual(events[-1]['data']['sections']['positive_ru'], 'Value POSITIVE_RU')
        self.assertEqual(events[-1]['data']['complete'], 12)
        self.assertEqual(len(self.mock.requests),2)
        self.assertEqual(self.mock.requests[0]['model'],'mock-qwen35')
        self.assertEqual(self.mock.requests[0]['messages'][1]['content'][1]['type'],'image_url')

    def test_video_pipeline(self):
        image='data:image/jpeg;base64,'+base64.b64encode(b'test-image').decode()
        images=[{'time':str(i),'data':image} for i in range(5)]
        body=json.dumps({'kind':'video','depth':'fast','target':'FramePack F1','images':images}).encode()
        req=urllib.request.Request(self.url+'/api/analyze',data=body,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r:
            events=[json.loads(x) for x in r.read().decode().splitlines()]
        self.assertEqual(events[-1]['data']['complete'],12)
        self.assertEqual(events[-1]['data']['kind'],'video')

    def test_reject_non_image(self):
        body=json.dumps({'kind':'photo','depth':'fast','images':[{'data':'http://example.com/image.png'}]}).encode()
        req=urllib.request.Request(self.url+'/api/analyze',data=body,headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as cm:urllib.request.urlopen(req,timeout=10)
        self.assertEqual(cm.exception.code,400)


if __name__=='__main__':unittest.main(verbosity=2)
