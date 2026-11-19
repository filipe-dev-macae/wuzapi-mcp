import asyncio
import base64
import hashlib
import json
import tempfile
from pathlib import Path
import unittest
import test_attendance
from aguaviva.attendance_media import capture,prepare,cleanup

class MediaTests(unittest.TestCase):
 setUp = test_attendance.AttendanceTests.setUp
 tearDown = test_attendance.AttendanceTests.tearDown
 event = test_attendance.AttendanceTests.event
 def media_event(self,kind,content=b'not media',own=False):
  value=json.loads(self.event('media',own=own))
  value['event']['Message']={kind:{'mimetype':'audio/ogg' if kind=='audioMessage' else 'image/jpeg'}}
  value['base64']=base64.b64encode(content).decode()
  return json.dumps(value).encode()
 def test_signed_event_preserves_audio_without_putting_bytes_in_queue(self):
  self.bridge.receive(self.media_event('audioMessage'),'application/json',self.now)
  with self.bridge.db() as db:
   payload=json.loads(db.execute('SELECT payload FROM events').fetchone()[0])
  self.assertEqual(payload['media_status'],'pending')
  self.assertNotIn('base64',payload)
  self.assertEqual((self.bridge.media_dir/(payload['media_id']+'.source')).read_bytes(),b'not media')
 def test_own_media_is_not_processed(self):
  self.bridge.receive(self.media_event('audioMessage',own=True),'application/json',self.now)
  self.assertFalse(self.bridge.media_dir.exists())
 def test_corrupt_audio_is_explicit_failure_and_source_removed(self):
  self.bridge.receive(self.media_event('audioMessage'),'application/json',self.now)
  asyncio.run(self.bridge.prepare_media(self.now))
  with self.bridge.db() as db: payload=json.loads(db.execute('SELECT payload FROM events').fetchone()[0])
  self.assertEqual(payload['media_status'],'processing_failed')
  self.assertFalse(list(self.bridge.media_dir.glob('*.source')))
 def test_actual_image_decoded_and_ready_for_agent(self):
  import io
  from PIL import Image
  buf=io.BytesIO();Image.new('RGB',(16,16),'blue').save(buf,format='JPEG');image=buf.getvalue()
  self.bridge.receive(self.media_event('imageMessage',image),'application/json',self.now)
  asyncio.run(self.bridge.prepare_media(self.now))
  with self.bridge.db() as db: payload=json.loads(db.execute('SELECT payload FROM events').fetchone()[0])
  self.assertEqual(payload['media_status'],'image_ready')
  self.assertTrue(Path(payload['media_path']).read_bytes().startswith(b'\xff\xd8'))
  latest=self.bridge.context('5511111111111@s.whatsapp.net',self.now)
  self.assertNotIn('não foi baixada',latest['history'][-1]['content'])
 def test_long_audio_is_not_truncated_silently(self):
  value=json.loads(self.media_event('audioMessage'));value['event']['Message']['audioMessage']['seconds']=301
  self.bridge.receive(json.dumps(value).encode(),'application/json',self.now)
  with self.bridge.db() as db: payload=json.loads(db.execute('SELECT payload FROM events').fetchone()[0])
  self.assertEqual(payload['media_status'],'audio_too_long')
 def test_duplicate_does_not_recreate_deleted_source(self):
  raw=self.media_event('audioMessage');self.bridge.receive(raw,'application/json',self.now)
  asyncio.run(self.bridge.prepare_media(self.now))
  self.bridge.receive(raw,'application/json',self.now)
  self.assertFalse(list(self.bridge.media_dir.glob('*.source')))

if __name__=='__main__': unittest.main()
