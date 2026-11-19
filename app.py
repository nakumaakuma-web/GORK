# -*- coding: utf-8 -*-
"""Prompt Extractor Studio: dependency-free local interface for llama.cpp."""
from __future__ import annotations

import argparse
import functools
import json
import os
import signal
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import updater
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LLAMA = os.getenv('PES_LLAMA_URL', 'http://127.0.0.1:8080').rstrip('/')
LIMIT_BYTES = 42 * 1024 * 1024
ANALYSIS_TOKENS = 2350
FINAL_TOKENS = 3700
FIELDS = [
    'APPEARANCE_RU', 'POSE_RU', 'CLOTHING_RU', 'STYLE_RU',
    'UNCERTAINTY_RU', 'POSITIVE_RU', 'POSITIVE_EN',
    'NEGATIVE_RU', 'NEGATIVE_EN', 'FRAMEPACK_RU', 'FRAMEPACK_EN',
    'TIMELINE_RU'
]

ANALYSIS_COMMON = """Ты эксперт по визуальному анализу изображений для обратного промптинга.
Опиши ТОЛЬКО наблюдаемое. Никогда не выдавай предположение за факт.
Лево и право — относительно самого человека, а не зрителя. Если сторона неясна, укажи неопределённость.
Возраст не угадывай точно; если совершеннолетие по изображению неочевидно — не утверждай его.
Разрешено объективно описывать видимую наготу/интимные детали взрослой сцены без выдумывания скрытого.
Текст только на русском, без рассуждений, без вызова инструментов; не упоминай названия моделей-генераторов как установленные факты.
Не навязывай качество 8K, masterpiece и другие неподтверждённые метки.
"""

PHOTO_FAST = ANALYSIS_COMMON + """
Исследуй приложенное ФОТО. Подробно и структурированно перечисли:
1. УСТОЙЧИВАЯ ВНЕШНОСТЬ: лицо, волосы, кожа, глаза, телосложение, татуировки/пирсинг, отличительные признаки.
2. ПОЗА И ГЕОМЕТРИЯ: ориентация тела, голова, руки, кисти, ноги (если видны), контакты с предметами.
3. ОДЕЖДА И ПРЕДМЕТЫ: видимые цвета, текстуры, детали и аксессуары.
4. СЦЕНА И ТЕХНИКА: фон, свет, ракурс, кадрирование, перспектива, степень реализма.
5. НЕОПРЕДЕЛЁННОСТИ: спорные и скрытые детали, которые нельзя утверждать.
Сохрани мелкие уникальные признаки, но избегай догадок. Дай законченный результат.
"""

PHOTO_FOCUS = {
    'appearance': ANALYSIS_COMMON + """Исследуй фотографию с максимальной точностью ТОЛЬКО в части внешности персонажей.
Отдели лицо (форма, нос, глаза, брови, губы, веснушки), волосы (цвета и зоны), кожу, пропорции, родинки, татуировки, пирсинг. Указывай место признака относительно тела, а не зрителя, если оно однозначно. Отдельно напиши, где деталь неразличима. Не описывай действия и не угадывай невидимые части тела.""",
    'geometry': ANALYSIS_COMMON + """Исследуй фотографию ТОЛЬКО по геометрии, позе, одежде и взаимодействиям. Опиши ориентацию каждого видимого человека, положение суставов, рук, пальцев, ног, корпуса, точку опоры, повороты, положение ткани и аксессуаров. Запиши ракурс относительно камеры. Не угадывай скрытые части тела и не путай лево/право человека и зрителя.""",
    'style': ANALYSIS_COMMON + """Исследуй фотографию ТОЛЬКО по стилю и окружению: композиция, план, перспектива, видимые предметы, освещение (направление, тени, характер), материалы и текстуры, цветовая палитра, степень рисованности/фотореализма. Опиши видимые отличительные признаки; не приписывай изображение конкретной нейросети.""",
}

VIDEO_FOCUS = ANALYSIS_COMMON + """
Тебе даны КЛЮЧЕВЫЕ КАДРЫ одного видео с временными метками. Это дискретная выборка, НЕ полный видеоряд.
Опиши на русском: а) видимую внешность/одежду; б) что меняется между показанными кадрами, с временными отметками; в) движения персонажей и камеры, если они обоснованы кадрами; г) стиль, свет; д) чего НЕЛЬЗЯ заключить по редким кадрам.
Не называй движение непрерывным, если между кадрами его не видно. Привязывай наблюдения к времени. Не домысливай скрытые действия.
"""

SYNTH = """Ты редактор промптов. На основе ТОЛЬКО данного ниже визуального анализа подготовь структурированный результат.
Принцип: российские и английские промпты должны быть эквивалентны по смыслу. Лево и право относительны персонажу. Не добавляй новые, не подтвержденные анализом детали.
Негативный промпт НЕ восстановлен из исходника: составь отдельно полезные запреты на типовые артефакты и потерю описанных уникальных признаков; не запрещай фактические черты персонажей.
Если исходник — видео: добавь короткий английский FramePack motion prompt (действия и камера, не перегружай внешностью) и русскую версию, а также хронологию по наблюдаемым кадрам.
Если фото: в FRAMEPACK_RU и FRAMEPACK_EN напиши «Не определено по одному кадру / Cannot infer motion from a still image» — не придумывай движение.

Выведи СТРОГО эти заголовки на отдельных строках, после каждого — содержательный текст, без вводных комментариев и Markdown-блоков кода:
===APPEARANCE_RU===
===POSE_RU===
===CLOTHING_RU===
===STYLE_RU===
===UNCERTAINTY_RU===
===POSITIVE_RU===
===POSITIVE_EN===
===NEGATIVE_RU===
===NEGATIVE_EN===
===FRAMEPACK_RU===
===FRAMEPACK_EN===
===TIMELINE_RU===

POSITIVE_RU / POSITIVE_EN должны быть самостоятельными готовыми позитивными промптами.
NEGATIVE_RU / NEGATIVE_EN должны быть самостоятельными негативными промптами.
Каждый раздел заполни; если информации нет, прямо укажи «Не видно / Not visible».
Не выводи рассуждения и вызовы инструментов. Проверяй перевод терминов (sheer ≠ fishnet, left ≠ right).

ТИП ИСХОДНИКА: {kind}
ЦЕЛЕВОЙ ГЕНЕРАТОР: {target}

ВИЗУАЛЬНЫЙ АНАЛИЗ:
{analysis}
"""


def _get_model_name() -> str:
    """Use the real ID advertised by the already running llama.cpp server."""
    try:
        with urllib.request.urlopen(LLAMA + '/v1/models', timeout=5) as response:
            data = json.load(response)
        models = data.get('data', [])
        if models and isinstance(models[0].get('id'), str):
            return models[0]['id']
    except Exception:
        pass
    # Older llama.cpp releases accept this OpenAI-compatible placeholder.
    return 'local-model'


def _llama_request(prompt: str, images: list[dict], max_tokens: int = 2400) -> str:
    contents = [{"type": "text", "text": prompt}]
    for item in images:
        stamp = str(item.get('time', '')).strip()
        if stamp:
            contents.append({"type": "text", "text": f"Ключевой кадр, время {stamp} сек:"})
        contents.append({"type": "image_url", "image_url": {"url": item['data']}})

    payload = {
        "model": _get_model_name(), "messages": [
            {"role": "system", "content": "Отвечай итоговым текстом, без инструментов. Русский язык, кроме запрошенных EN-разделов."},
            {"role": "user", "content": contents},
        ],
        "max_tokens": max_tokens, "temperature": 0.15, "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    raw = _post_llama(payload)
    try:
        data = json.loads(raw)
        choices = data['choices']
        message = choices[0]['message']
        content = message.get('content')
        if isinstance(content, list):
            content = '\n'.join(x.get('text', '') for x in content if isinstance(x, dict))
        if not content or not str(content).strip():
            raise RuntimeError('Модель не вернула итоговый текст; возможно, весь лимит ушёл на рассуждения. Проверь Thinking в llama.cpp.')
        content = re.sub(r'<think>.*?</think>', '', str(content), flags=re.S)
        if not content.strip():
            raise RuntimeError('Модель вернула только рассуждения. Нужна настройка Thinking в llama.cpp.')
        return content.strip()
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise RuntimeError('Неожиданный ответ llama.cpp: ' + raw[:700]) from exc


def _post_llama(payload: dict) -> str:
    def request(body):
        encoded = json.dumps(body, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(LLAMA + '/v1/chat/completions', data=encoded,
                                     headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=1200) as resp:
            return resp.read().decode('utf-8', errors='replace')
    try:
        return request(payload)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:600]
        # Support older llama.cpp builds that don't accept template kwargs.
        if exc.code in (400, 422) and 'chat_template_kwargs' in payload:
            second = dict(payload)
            second.pop('chat_template_kwargs', None)
            try:
                return request(second)
            except urllib.error.HTTPError as inner:
                raise RuntimeError(f'llama.cpp HTTP {inner.code}: {inner.read().decode("utf-8",errors="replace")[:600]}') from inner
        raise RuntimeError(f'llama.cpp HTTP {exc.code}: {detail}') from exc
    except urllib.error.URLError as exc:
        raise RuntimeError('Не удалось подключиться к llama.cpp на 127.0.0.1:8080. Запусти сервер модели и проверь порт.') from exc


def parse_sections(content: str) -> dict:
    marker = re.compile(r'^\s*={3}\s*(' + '|'.join(map(re.escape, FIELDS)) + r')\s*={3}\s*$', re.I | re.M)
    pieces = list(marker.finditer(content))
    result = {key.lower(): '' for key in FIELDS}
    for ix, match in enumerate(pieces):
        start = match.end()
        end = pieces[ix+1].start() if ix+1 < len(pieces) else len(content)
        result[match.group(1).lower()] = content[start:end].strip()
    return result


def validate_images(images):
    if not isinstance(images, list) or not 1 <= len(images) <= 8:
        raise ValueError('Нужно от 1 до 8 изображений/кадров.')
    for frame in images:
        if not isinstance(frame, dict):
            raise ValueError('Некорректные данные кадра.')
        s = frame.get('data', '')
        if not isinstance(s, str) or not s.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,')):
            raise ValueError('Поддерживаются PNG/JPEG/WebP в base64.')
        if len(s) > 12_000_000:
            raise ValueError('Слишком большой кадр — уменьшите разрешение.')


class Handler(BaseHTTPRequestHandler):
    server_version = 'PromptExtractorStudio/0.3'

    def log_message(self, fmt, *args):
        print('[PES] ' + fmt % args)

    def _reply(self, status, body: bytes, content_type='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == '/':
            data = (ROOT / 'ui' / 'index.html').read_bytes()
            return self._reply(200, data, 'text/html; charset=utf-8')
        if path == '/ui.js':
            return self._reply(200, (ROOT / 'ui' / 'ui.js').read_bytes(), 'text/javascript; charset=utf-8')
        if path == '/api/update/check':
            try:
                result = updater.check(ROOT)
                result.pop('manifest', None)  # Never expose raw update file listings to UI.
                result.pop('manifest_url', None)
                return self._reply(200, json.dumps(result, ensure_ascii=False).encode())
            except updater.UpdateError as exc:
                return self._reply(200, json.dumps({'status': 'error', 'message': str(exc), 'current': updater.VERSION}, ensure_ascii=False).encode())
        if path == '/health':
            healthy = False
            status = 'недоступна'
            try:
                with urllib.request.urlopen(LLAMA + '/health', timeout=3) as response:
                    raw = response.read().decode('utf-8', errors='replace')
                    healthy = response.status == 200
                    status = 'готова' if healthy else ('загружается' if response.status == 503 else raw[:100])
            except urllib.error.HTTPError as exc:
                status = 'загружается' if exc.code == 503 else f'HTTP {exc.code}'
            except Exception:
                pass
            return self._reply(200, json.dumps({'ready': healthy, 'status': status, 'llama': LLAMA}).encode())
        return self._reply(404, b'{}')

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == '/api/update/install':
            origin = self.headers.get('Origin', '')
            allowed_origins = {'http://127.0.0.1:%s' % self.server.server_address[1],
                               'http://localhost:%s' % self.server.server_address[1]}
            if origin not in allowed_origins or self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                return self._reply(403, b'{"error":"Local UI origin and JSON required"}')
            try:
                outcome = updater.install(ROOT)
                payload = json.dumps(outcome, ensure_ascii=False).encode()
                self._reply(200, payload)
                # Exit code 23 prompts start-studio.cmd to restart the app.
                # No restart if app is launched manually (tell user to relaunch).
                threading.Timer(1.0, lambda: os._exit(23)).start()
                return
            except updater.UpdateError as exc:
                return self._reply(400, json.dumps({'error': str(exc)}, ensure_ascii=False).encode())
        if path != '/api/analyze':
            return self._reply(404, b'{}')
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 1 or length > LIMIT_BYTES:
                return self._reply(413, b'{"error":"Too much data"}')
            data = json.loads(self.rfile.read(length))
            images = data['images']
            validate_images(images)
            kind = data.get('kind', 'photo')
            if kind not in ('photo', 'video'):
                raise ValueError('Неизвестный тип исходника.')
            depth = data.get('depth', 'fast')
            if depth not in ('fast', 'deep'):
                raise ValueError('Неизвестный режим.')
            target = str(data.get('target', 'Общий генератор'))[:100]
        except (ValueError, TypeError, KeyError) as exc:
            return self._reply(400, json.dumps({'error': str(exc)}, ensure_ascii=False).encode())

        # NDJSON streaming allows the UI to show the current stage.
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()

        def notify(event, **kwargs):
            line = (json.dumps({'event': event, **kwargs}, ensure_ascii=False) + '\n').encode('utf-8')
            try:
                self.wfile.write(line)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

        try:
            notify('stage', message='Проверка подключения Qwen…')
            # No web tools and no external API: only localhost.
            observations = []
            if kind == 'photo':
                if depth == 'fast':
                    notify('stage', message='Анализ фотографии…')
                    observations.append(_llama_request(PHOTO_FAST, images[:1], ANALYSIS_TOKENS))
                else:
                    for label, focus in [('Внешность', 'appearance'), ('Поза и одежда', 'geometry'), ('Стиль и окружение', 'style')]:
                        notify('stage', message='Подробный анализ: ' + label)
                        observations.append(f'{label}:\n' + _llama_request(PHOTO_FOCUS[focus], images[:1], ANALYSIS_TOKENS))
            else:
                # Split temporal sequence into small batches for a 16k context window.
                step = 3 if depth == 'deep' else 4
                for start in range(0, len(images), step):
                    batch = images[start:start + step]
                    notify('stage', message=f'Анализ кадров {start + 1}–{start + len(batch)} из {len(images)}…')
                    observations.append(_llama_request(VIDEO_FOCUS, batch, ANALYSIS_TOKENS))

            analysis = '\n\n'.join(observations)
            if len(analysis) > 20000:
                analysis = analysis[:20000] + '\n[длинный анализ обрезан]'
            notify('stage', message='Сборка позитивных и негативных промптов RU/EN…')
            completed = _llama_request(SYNTH.format(kind=kind, target=target, analysis=analysis), [], FINAL_TOKENS)
            sections = parse_sections(completed)
            notify('done', data={
                'kind': kind, 'depth': depth, 'target': target, 'sections': sections,
                'raw': completed, 'source_analysis': analysis,
                'complete': sum(bool(x) for x in sections.values()), 'total': len(FIELDS),
                'note': 'Промпты реконструированы; негативный промпт составлен, а не извлечён из файла.'
            })
        except Exception as exc:
            notify('error', message=str(exc))


def main():
    parser = argparse.ArgumentParser(description='Prompt Extractor Studio local UI')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    url = f'http://127.0.0.1:{args.port}'
    print('Prompt Extractor Studio v0.3')
    print('Интерфейс:', url)
    print('Qwen llama.cpp:', LLAMA)
    print('Работает локально. Для остановки нажми Ctrl+C.')
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
