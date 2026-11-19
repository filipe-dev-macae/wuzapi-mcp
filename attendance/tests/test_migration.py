import json
import sqlite3
import pytest
import test_attendance
from aguaviva.backup import snapshot,restore,exclusive
from aguaviva.attendance_bridge import Attendance


def test_relocate_preserves_pause_dedup_and_media(tmp_path):
    t=test_attendance.AttendanceTests();t.setUp()
    try:
        t.receive('received');t.receive('human',True)
        media=t.bridge.media_dir;media.mkdir();ident='a'*64;(media/(ident+'.jpg')).write_bytes(b'image')
        with t.bridge.db() as db:
            value=json.loads(db.execute('select payload from events').fetchone()[0])
            value.update(media_id=ident,media_path=str(media/(ident+'.jpg')))
            db.execute('update events set payload=?',(json.dumps(value),))
            db.execute('insert into outgoing values(?,?,?,?)',('persisted','5511111111111@s.whatsapp.net','uncertain',t.now))
        # Existing fixture DB name differs from deployed DB name.
        (t.root/'queue.sqlite').rename(t.root/'bridge.sqlite')
        snapshot(t.root,tmp_path/'backup');restore(tmp_path/'backup',tmp_path/'destination')
        restored=Attendance(t.config,tmp_path/'destination/bridge.sqlite')
        assert restored.context('5511111111111@s.whatsapp.net',t.now)['human_until']==t.now+300
        assert not restored.receive(t.event('received'),'application/json',t.now)
        with restored.db() as db:
            assert db.execute('select state from outgoing').fetchone()[0]=='uncertain'
            value=json.loads(db.execute('select payload from events').fetchone()[0])
            assert str(tmp_path/'destination') in value['media_path']
        assert (tmp_path/'destination/media-inbox'/(ident+'.jpg')).exists()
    finally:t.tearDown()


def test_backup_refuses_active_consumer(tmp_path):
    with exclusive(tmp_path):
        with pytest.raises(BlockingIOError):snapshot(tmp_path,tmp_path/'copy')
