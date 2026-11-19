"""Private, bounded media ingestion for signed restaurant events."""
import asyncio
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from .media_worker import process_media
POOL = ProcessPoolExecutor(max_workers=1,mp_context=multiprocessing.get_context('spawn'))
import base64
import json
import os
from pathlib import Path
import re
import time

MAX_BYTES = 12 * 1024 * 1024

def media_message(value):
    message = value.get('event', {}).get('Message', {})
    for _ in range(3):
        wrapper = next((message[k] for k in ('ephemeralMessage','viewOnceMessage','viewOnceMessageV2') if k in message), None)
        if wrapper is None: break
        message = wrapper.get('message', {})
    return message

def capture(value, payload, key, directory):
    kind = payload['kind']
    if kind not in ('audioMessage','imageMessage'): return
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    node = media_message(value).get(kind, {})
    if kind == 'audioMessage' and int(node.get('seconds',0)) > 300:
        payload['media_status'] = 'audio_too_long'; return
    source = directory / (key + '.source')
    encoded = value.get('base64')
    if isinstance(encoded, str) and encoded:
        if encoded.startswith('data:'): encoded = encoded.split(',',1)[1]
        if len(encoded) > MAX_BYTES * 4 // 3 + 8:
            payload['media_status'] = 'too_large'; return
        try:
            data = base64.b64decode(encoded, validate=True)
            if not data or len(data) > MAX_BYTES: raise ValueError('media size')
            with source.open('wb') as f: os.chmod(source,0o600); f.write(data)
            payload['media_status'] = 'pending'
        except (ValueError, TypeError): payload['media_status'] = 'invalid_media'
    else:
        # The media keys remain private; never place them in the agent event.
        mapping = {'URL':'Url','directPath':'DirectPath','mediaKey':'MediaKey','mimetype':'Mimetype','fileEncSHA256':'FileEncSHA256','fileSHA256':'FileSHA256','fileLength':'FileLength'}
        body = {target:node[key] for key,target in mapping.items() if key in node}
        if {'Url','MediaKey','Mimetype','FileSHA256','FileLength'} <= body.keys() and int(body['FileLength']) <= MAX_BYTES:
            # Only WhatsApp media download references, never arbitrary customer URLs.
            from urllib.parse import urlsplit
            host = urlsplit(body['Url']).hostname or ''
            if not (host == 'mmg.whatsapp.net' or host.endswith('.whatsapp.net')):
                payload['media_status'] = 'invalid_media_host'; return
            request = directory / (key + '.request.json')
            request.write_text(json.dumps(body)); request.chmod(0o600)
            payload['media_status'] = 'download_pending'
        else: payload['media_status'] = 'missing_media'
    payload['media_id'] = key

async def prepare(payload, directory, download):
    status = payload.get('media_status')
    if status not in ('pending','download_pending'): return
    key = payload.get('media_id','')
    if not re.fullmatch('[a-f0-9]{64}',key): raise ValueError('invalid local media id')
    source = directory / (key + '.source')
    request = directory / (key + '.request.json')
    keep_source=False
    try:
        if status == 'download_pending':
            data = await download(payload['kind'],json.loads(request.read_text()))
            if not data or len(data) > MAX_BYTES: raise ValueError('media size')
            source.write_bytes(data); source.chmod(0o600)
        output = directory / (key + '.jpg')
        result = await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(POOL,process_media,payload['kind'],str(source),str(output)),240)
        if payload['kind'] == 'audioMessage':
            text = result['transcript'].strip()
            if not text: raise ValueError('no intelligible speech')
            payload['text'] = text[:12000]
            payload['media_status'] = 'transcribed'
        else:
            payload['media_path'] = str(output)
            payload['media_status'] = 'image_ready'
            if payload['text'].startswith('Mídia recebida;'): payload['text'] = 'Foto recebida; analise o arquivo media_path antes de responder.'
    except asyncio.CancelledError:
        keep_source=True
        raise
    except Exception:
        payload['media_status'] = 'processing_failed'
    finally:
        if not keep_source:
            source.unlink(missing_ok=True); request.unlink(missing_ok=True)


def cleanup(directory):
    if directory.exists():
        for path in directory.iterdir():
            if re.fullmatch(r'[a-f0-9]{64}\.(source|jpg|request\.json)',path.name) and time.time()-path.stat().st_mtime > 86400:
                path.unlink()
