import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from aguaviva.attendance_bridge import Attendance

class AttendanceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.config=self.root/'config.json'
  self.config.write_text(json.dumps({'dispatch_enabled':False,'policy_approved':True,'allow_all_private':True,'agent_id':'test_agent','instance_ids':['store'],'allowed_chats':[]})); self.config.chmod(0o600)
  self.bridge=Attendance(self.config,self.root/'queue.sqlite'); self.now=1800000000
 def tearDown(self): self.tmp.cleanup()
 def event(self,ident,own=False,chat='5511111111111@s.whatsapp.net',at=None,text='quero quentinha'):
  return json.dumps({'type':'Message','userID':'store','event':{'Info':{'Chat':chat,'Sender':chat,'IsFromMe':own,'IsGroup':False,'ID':ident,'Timestamp':datetime.fromtimestamp(at or self.now,timezone.utc).isoformat()},'Message':{'conversation':text}}}).encode()
 def receive(self,*args,now=None,**kw): return self.bridge.receive(self.event(*args,**kw),'application/json',now or self.now)
 def test_incoming_and_duplicate(self):
  self.assertTrue(self.receive('a')); self.assertFalse(self.receive('a'))
  with self.bridge.db() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
 def test_human_holds_and_rechecks(self):
  self.receive('a'); self.receive('h',True)
  self.assertEqual(self.bridge.context('5511111111111@s.whatsapp.net',self.now)['human_until'],self.now+300)
  asyncio.run(self.bridge.step(self.now+299))
  with self.bridge.db() as db: self.assertEqual({r[0] for r in db.execute('SELECT state FROM events')},{'human_paused'})
  asyncio.run(self.bridge.step(self.now+300))
  with self.bridge.db() as db: self.assertEqual({r[0] for r in db.execute('SELECT state FROM events')},{'pending'})
 def test_new_human_restarts_window(self):
  self.receive('a'); self.receive('h',True); self.receive('h2',True,at=self.now+200,now=self.now+200)
  self.assertEqual(self.bridge.context('5511111111111@s.whatsapp.net',self.now)['human_until'],self.now+500)
 def test_older_human_does_not_shorten_window(self):
  self.receive('h',True); self.receive('old',True,at=self.now-100)
  self.assertEqual(self.bridge.context('5511111111111@s.whatsapp.net',self.now)['human_until'],self.now+300)
 def test_registered_bot_does_not_pause(self):
  chat='5511111111111@s.whatsapp.net'
  with self.bridge.db() as db: db.execute('INSERT INTO outgoing VALUES(?,?,?,?)',('bot',chat,'attempting',self.now))
  self.receive('bot',True)
  self.assertEqual(self.bridge.context(chat,self.now)['human_until'],0)
 def test_human_pause_is_per_chat(self):
  self.receive('a'); self.receive('h',True); self.receive('b',chat='5522222222222@s.whatsapp.net')
  asyncio.run(self.bridge.step(self.now))
  with self.bridge.db() as db:
   pending=[json.loads(r[0])['chat_jid'] for r in db.execute("SELECT payload FROM events WHERE state='pending'")]
  self.assertEqual(pending,['5522222222222@s.whatsapp.net'])
 def test_restart_keeps_human_pause(self):
  self.receive('h',True); other=Attendance(self.config,self.root/'queue.sqlite')
  self.assertEqual(other.context('5511111111111@s.whatsapp.net',self.now)['human_until'],self.now+300)
 def test_later_human_recheck_uses_new_delivery_key(self):
  self.receive('a')
  with self.bridge.db() as db: db.execute("UPDATE events SET state='completed'")
  self.receive('human1',True)
  with self.bridge.db() as db:
   first=db.execute("SELECT id FROM events WHERE id LIKE 'human-%'").fetchone()[0]
   db.execute("UPDATE events SET state='completed'")
  self.receive('human2',True,at=self.now+100,now=self.now+100)
  with self.bridge.db() as db: second=db.execute("SELECT id FROM events WHERE state='pending'").fetchone()[0]
  self.assertNotEqual(first,second)
 def test_new_question_supersedes_old_human_recheck(self):
  self.receive('a')
  with self.bridge.db() as db: db.execute("UPDATE events SET state='completed'")
  self.receive('human',True); self.receive('newquestion',text='vem com arroz?')
  with self.bridge.db() as db:
   self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE state='superseded'").fetchone()[0],1)
   self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE state='pending'").fetchone()[0],1)
 def test_verified_alias_unifies_human_and_customer(self):
  c=json.loads(self.config.read_text()); c['chat_aliases']={'5511111111111@s.whatsapp.net':'1234@lid'};self.config.write_text(json.dumps(c))
  self.receive('incoming',chat='1234@lid'); self.receive('human',True)
  self.assertEqual(self.bridge.context('1234@lid',self.now)['human_until'],self.now+300)
 def test_old_event_ignored(self): self.assertFalse(self.receive('old',at=self.now-301))
 def test_disabled_action_refuses(self):
  with self.assertRaisesRegex(ValueError,'disabled'): asyncio.run(self.bridge.action({'chat_jid':'5511111111111@s.whatsapp.net','operation':'text','body':{'Body':'Olá'}}))
if __name__=='__main__': unittest.main()
