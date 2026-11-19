# -*- coding: utf-8 -*-
"""Minimal, dependency-free updater for Prompt Extractor Studio.

The update channel is deliberately NOT preconfigured. Only a user-selected
HTTPS manifest is allowed. A SHA256 check protects transfer integrity; it is
not a cryptographic publisher signature. Keep the update URL trusted.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = '0.7.0'
CONFIG_NAME = 'update_config.json'
DEFAULT_MANIFEST_URL = 'https://raw.githubusercontent.com/nakumaakuma-web/GORK/main/update-manifest.json'
# Files deliberately limited; models, user data, saved results and configs untouched.
UPDATEABLE = frozenset({
    'app.py', 'updater.py', 'ui/index.html', 'ui/ui.js',
    'start-all.cmd', 'start-studio.cmd', 'README_RU.md',
    'tests/test_app.py', 'tests/test_updater.py',
})
MAX_BYTES_PER_FILE = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_FILES = 25


class UpdateError(Exception):
    """Controlled, user-displayable update error."""


def config(root: Path = ROOT) -> dict:
    path = root / CONFIG_NAME
    if not path.is_file():
        return {'manifest_url': DEFAULT_MANIFEST_URL}
    try:
        obj = json.loads(path.read_text(encoding='utf-8-sig'))
        if isinstance(obj, dict):
            # v0.2 kept this file empty until a repository was connected.
            # The user may override the default by setting an explicit URL.
            if not str(obj.get('manifest_url', '')).strip():
                obj['manifest_url'] = DEFAULT_MANIFEST_URL
            return obj
    except (OSError, ValueError):
        pass
    raise UpdateError('Повреждён update_config.json. Проверь конфигурацию обновлений.')


def _version_tuple(text: str) -> tuple[int, ...]:
    if not isinstance(text, str) or not re.fullmatch(r'\d+(?:\.\d+){1,3}', text):
        raise UpdateError('Неверный номер версии в манифесте.')
    return tuple(map(int, text.split('.')))


def _get(url: str, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={'User-Agent': 'PromptExtractorStudio/' + VERSION, 'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
    try:
        with urllib.request.urlopen(request, timeout=20) as res:
            if not _trusted_url(res.geturl()):
                raise UpdateError('Обновление перенаправлено на неподдерживаемый адрес.')
            if res.headers.get('Content-Length') and int(res.headers['Content-Length']) > limit:
                raise UpdateError('Файл обновления слишком большой.')
            data = res.read(limit + 1)
    except UpdateError:
        raise
    except Exception as exc:
        raise UpdateError('Не удалось загрузить обновление: ' + str(exc)) from exc
    if len(data) > limit:
        raise UpdateError('Файл обновления превышает допустимый размер.')
    return data


def _trusted_url(url: str) -> bool:
    p = urllib.parse.urlsplit(url)
    return p.scheme == 'https' and p.hostname in {
        'raw.githubusercontent.com', 'github.com', 'objects.githubusercontent.com'
    } and not p.username and not p.password and not p.fragment


def _uncached_manifest_url(url: str) -> str:
    # A version-independent cache-buster avoids stale raw.githubusercontent.com
    # manifests when a new GitHub release was pushed only minutes ago.
    p = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    query = [(k, v) for k,v in query if k != 'pes_check']
    query.append(('pes_check', str(time.time_ns())))
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(query), p.fragment))


def check(root: Path = ROOT) -> dict:
    settings = config(root)
    url = str(settings.get('manifest_url', '')).strip()
    if not url:
        return {'status': 'not_configured', 'current': VERSION,
                'message': 'Источник обновлений не настроен.'}
    if not _trusted_url(url):
        raise UpdateError('Допускается только HTTPS-манифест на GitHub. Проверь update_config.json.')
    try:
        manifest = json.loads(_get(_uncached_manifest_url(url), MAX_MANIFEST_BYTES).decode('utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise UpdateError('Некорректный JSON манифеста.') from exc
    if not isinstance(manifest, dict) or manifest.get('application') != 'prompt-extractor-studio':
        raise UpdateError('Манифест не относится к Prompt Extractor Studio.')
    version = manifest.get('version', '')
    current = _version_tuple(VERSION)
    remote = _version_tuple(version)
    files = manifest.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise UpdateError('Неверный список файлов обновления.')
    names, total = set(), 0
    for item in files:
        if not isinstance(item, dict):
            raise UpdateError('Некорректная запись файла обновления.')
        path = item.get('path', '')
        digest = item.get('sha256', '')
        size = item.get('size', 0)
        if path not in UPDATEABLE or path in names:
            raise UpdateError('Запрещённый или повторный путь обновления: ' + str(path))
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise UpdateError('Некорректная контрольная сумма: ' + path)
        if not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= MAX_BYTES_PER_FILE:
            raise UpdateError('Неверный размер файла: ' + path)
        names.add(path)
        total += size
    if total > MAX_TOTAL_BYTES:
        raise UpdateError('Обновление превышает лимит размера.')
    return {'status': 'available' if remote > current else 'up_to_date',
            'current': VERSION, 'remote': version, 'manifest': manifest,
            'manifest_url': url, 'message': str(manifest.get('notes', ''))[:300]}


def install(root: Path = ROOT, info: dict | None = None) -> dict:
    """Download, verify, install with rollback and never touch unrelated files."""
    info = info or check(root)
    if info.get('status') != 'available':
        raise UpdateError('Новой версии нет.')
    base_url = info['manifest_url']
    base = urllib.parse.urlsplit(base_url)
    manifest = info['manifest']
    root = root.resolve()
    stage = Path(tempfile.mkdtemp(prefix='.update-', dir=root))
    backup = root / '.update_backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    modified: list[tuple[Path, Path | None]] = []
    try:
        for item in manifest['files']:
            rel = item['path']
            url = urllib.parse.urljoin(base_url, rel)
            p = urllib.parse.urlsplit(url)
            # Same origin and path directory. Blocks off-origin manifest injection.
            if not _trusted_url(url) or p.netloc != base.netloc or not p.path.startswith(base.path.rsplit('/', 1)[0] + '/'):
                raise UpdateError('Файл обновления с другого источника: ' + rel)
            data = _get(url, MAX_BYTES_PER_FILE)
            if len(data) != item['size'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                raise UpdateError('Не совпадает SHA-256 или размер: ' + rel)
            dest = stage / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        # Validate Python syntax before touching current installation.
        for path in stage.rglob('*.py'):
            compile(path.read_bytes(), str(path), 'exec')
        backup.mkdir(parents=True, exist_ok=True)
        for item in manifest['files']:
            rel = item['path']
            destination = root / rel
            source = stage / rel
            previous = backup / rel if destination.exists() else None
            if previous:
                previous.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, previous)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            modified.append((destination, previous))
    except Exception as exc:
        for destination, previous in reversed(modified):
            if previous and previous.is_file():
                shutil.copy2(previous, destination)
            else:
                destination.unlink(missing_ok=True)
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError('Ошибка установки; выполнен откат: ' + str(exc)) from exc
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return {'status': 'installed', 'version': manifest['version'], 'backup': str(backup)}
