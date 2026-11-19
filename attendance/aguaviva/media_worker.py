"""Decode only local captured media; stdout is a bounded JSON result."""
import json
import sys
from pathlib import Path

import os
MODEL = None

def process_media(kind, source, output):
    global MODEL
    if kind == 'audioMessage':
        import av
        with av.open(source) as container:
            if container.duration is None or container.duration / av.time_base > 300:
                raise ValueError('audio duration exceeds five minutes or is unknown')
        from faster_whisper import WhisperModel
        if MODEL is None:
            MODEL = WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=1,download_root=os.environ.get('ATTENDANCE_MODELS','/data/models'),local_files_only=True)
        model = MODEL
        segments,info = model.transcribe(source,language='pt',beam_size=5,vad_filter=True)
        text = ' '.join(s.text.strip() for s in segments if s.no_speech_prob < 0.6)
        return {'transcript':text[:12000]}
    elif kind == 'imageMessage':
        from PIL import Image,ImageOps
        Image.MAX_IMAGE_PIXELS = 20_000_000
        with Image.open(source) as image:
            image.load()
            image = ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((2048,2048))
            image.save(output,'JPEG',quality=90)
        Path(output).chmod(0o600)
        return {'image_ready':True}
    else: raise ValueError('unsupported media')
