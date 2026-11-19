import asyncio
import json
import time
from types import SimpleNamespace
import pytest
import httpx2 as httpx
import test_attendance
from aguaviva.attendance_bridge import app_for
from aguaviva.connector import app_for as connector_app
from aguaviva.bridge import private_text

@pytest.fixture
def setup():
    t=test_attendance.AttendanceTests();t.setUp()
    t.now=time.time()
    c=json.loads(t.config.read_text());c.update(dispatch_enabled=True)
    t.config.write_text(json.dumps(c))
    t.receive('incoming')
    with t.bridge.db() as db:db.execute("UPDATE events SET state='submitted'")
    yield t
    t.tearDown()

def action(t, **kw):
    return dict(chat_jid='5511111111111@s.whatsapp.net',event_id='incoming',action_id='answer-1',operation='text',body={'Body':'Olá'},**kw)

@pytest.mark.parametrize('required,supplied,expected', [
    (True, None, True), (True, False, True), (True, True, True),
    (False, None, None), (False, False, False), (False, True, True),
])
async def test_preview_policy_is_per_deployment_and_preserves_idempotency(setup, required, supplied, expected):
    t=setup;calls=[]
    cfg=json.loads(t.config.read_text());cfg['require_link_preview']=required;t.config.write_text(json.dumps(cfg))
    async def send(v):calls.append(v);return SimpleNamespace(is_error=False,data={},content=[])
    t.bridge.call_mcp=send
    request=action(t);request['body']={'Body':'Veja https://example.com/produto'}
    if supplied is not None:request['body']['LinkPreview']=supplied
    assert (await t.bridge.action(request))['status']=='accepted'
    assert (await t.bridge.action(request))['status']=='accepted'
    assert len(calls)==1 and calls[0]['body'].get('LinkPreview') is expected
    assert request['body'].get('LinkPreview') is supplied

@pytest.mark.parametrize('operation,body', [
    ('presence', {'State':'composing'}),
    ('carousel', {'Body':'Opções','Cards':[]}),
    ('buttons', {'Body':'Opção','Buttons':[]}),
])
async def test_preview_policy_does_not_add_unsupported_fields_to_other_operations(setup, monkeypatch, operation, body):
    import datetime
    class DuringBusinessHours(datetime.datetime):
        @classmethod
        def now(cls, tz=None):return cls(2026,11,17,12,tzinfo=tz)
    monkeypatch.setattr(datetime, 'datetime', DuringBusinessHours)
    t=setup;calls=[]
    cfg=json.loads(t.config.read_text());cfg['require_link_preview']=True;t.config.write_text(json.dumps(cfg))
    async def send(v):calls.append(v);return SimpleNamespace(is_error=False,data={},content=[])
    t.bridge.call_mcp=send
    request=action(t);request.update(operation=operation,body=body)
    assert (await t.bridge.action(request))['status']=='accepted'
    assert 'LinkPreview' not in calls[0]['body']

def test_preview_configuration_requires_boolean(setup):
    from aguaviva.bridge import settings
    t=setup;cfg=json.loads(t.config.read_text());cfg['require_link_preview']='false';t.config.write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='require_link_preview'):settings(t.config)

async def test_duplicate_action_and_restart_no_resend(setup):
    t=setup;calls=[]
    async def send(v):calls.append(v);return SimpleNamespace(is_error=False,data={},content=[])
    t.bridge.call_mcp=send
    a=await t.bridge.action(action(t));b=await t.bridge.action(action(t))
    assert a['message_id']==b['message_id'];assert len(calls)==1
    from aguaviva.attendance_bridge import Attendance
    restarted=Attendance(t.config,t.root/'queue.sqlite');restarted.call_mcp=send
    assert (await restarted.action(action(t)))['status']=='accepted';assert len(calls)==1

async def test_timeout_is_persistent_and_not_replayed(setup):
    t=setup;calls=[]
    async def send(v):calls.append(v);raise TimeoutError()
    t.bridge.call_mcp=send
    assert (await t.bridge.action(action(t)))['status']=='uncertain'
    assert (await t.bridge.action(action(t)))['status']=='uncertain';assert len(calls)==1

async def test_human_receipt_is_not_blocked_by_slow_network(setup):
    t=setup;entered=asyncio.Event();release=asyncio.Event()
    async def send(v):entered.set();await release.wait();return SimpleNamespace(is_error=False,data={},content=[])
    t.bridge.call_mcp=send
    task=asyncio.create_task(t.bridge.action(action(t)));await entered.wait()
    # Real webhook uses this lock: recording the human intervention must remain possible.
    async with asyncio.timeout(1):
        async with t.bridge.lock:t.receive('human',True)
    release.set();await task
    later=action(t);later['action_id']='answer-2'
    assert (await t.bridge.action(later))['status']=='human_paused'

async def test_stale_question_cannot_send(setup):
    t=setup;t.receive('new')
    assert (await t.bridge.action(action(t)))['status']=='stale_event'

async def test_connector_denies_other_agents_approvals_and_auth(tmp_path):
    def secret(name,text):
        p=tmp_path/name;p.write_text(text);p.chmod(0o600);return p
    key=secret('shared','k'*40);secret('url','http://127.0.0.1:1234');secret('token','t'*40)
    calls=[]
    def handle(r):calls.append(r);return httpx.Response(200,json={'status':'completed'})
    app=connector_app('agent-test',tmp_path,key,httpx.MockTransport(handle))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as c:
        body={'method':'GET','path':'/v1/agents/agent-test/deliveries/delivery-1'}
        assert (await c.post('/invoke',json=body)).status_code==401
        headers={'Authorization':'Bearer '+'k'*40}
        assert (await c.post('/invoke',json=body,headers=headers)).status_code==200
        for path in ['/v1/agents/other/messages','/v1/agents/agent-test/context/clear','/v1/agents/agent-test/approvals/a/respond']:
            assert (await c.post('/invoke',json={'method':'POST','path':path,'body':{}},headers=headers)).status_code==403
    assert len(calls)==1

async def test_signed_webhook_duplicate_and_signature(setup):
    import hmac,hashlib
    t=setup;key=t.root/'hmac';key.write_text('h'*40);key.chmod(0o600)
    cfg=json.loads(t.config.read_text());cfg['hmac_key_file']=str(key);t.config.write_text(json.dumps(cfg))
    raw=t.event('webhook')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app_for(t.bridge)),base_url='http://test') as c:
        assert (await c.post('/webhook',content=raw,headers={'content-type':'application/json'})).status_code==401
        headers={'content-type':'application/json','x-hmac-signature':hmac.new(b'h'*40,raw,hashlib.sha256).hexdigest()}
        assert (await c.post('/webhook',content=raw,headers=headers)).json()['status']=='accepted'
        assert (await c.post('/webhook',content=raw,headers=headers)).json()['status']=='ignored'

async def test_action_id_cannot_change_body(setup):
    t=setup
    async def send(v):return SimpleNamespace(is_error=False,data={},content=[])
    t.bridge.call_mcp=send
    await t.bridge.action(action(t))
    changed=action(t);changed['body']={'Body':'Outra resposta'}
    with pytest.raises(ValueError,match='different content'):await t.bridge.action(changed)

async def test_text_dispatch_bypasses_other_chat_media(setup):
    t=setup
    cfg=json.loads(t.config.read_text());policy=t.root/'policy';policy.write_text('Política compacta de teste.');policy.chmod(0o600)
    cfg['instruction_file']=str(policy);t.config.write_text(json.dumps(cfg))
    with t.bridge.db() as db:
        db.execute('delete from events')
        payload={'chat_jid':'100@lid','instance_id':'store','message_id':'media','kind':'audioMessage','media_status':'pending','text':'audio'}
        db.execute('insert into events(id,payload,created,updated) values(?,?,?,?)',('media',json.dumps(payload),t.now-1,t.now-1))
    t.receive('text',chat='200@lid')
    calls=[]
    async def api(config,method,path,body=None):
        calls.append(body)
        return httpx.Response(202,json={'deliveries':[{'id':'delivery-test','recipientAgentId':'test_agent'}]})
    t.bridge.openbot=api
    await t.bridge.step(t.now)
    assert len(calls)==1 and '200@lid' in calls[0]['text']
    assert 'ATENDIMENTO.md' not in calls[0]['text']

async def test_serial_dispatch_recovers_completed_receipt(setup):
    t=setup;t.receive('second')
    with t.bridge.db() as db:db.execute("UPDATE events SET state='pending'")
    cfg=json.loads(t.config.read_text());policy=t.root/'policy';policy.write_text('Teste');policy.chmod(0o600)
    cfg['instruction_file']=str(policy);t.config.write_text(json.dumps(cfg))
    methods=[]
    async def api(config,method,path,body=None):
        methods.append(method)
        return httpx.Response(202,json={'deliveries':[{'id':'delivery-test','recipientAgentId':'test_agent'}]}) if method=='POST' else httpx.Response(200,json={'status':'completed'})
    t.bridge.openbot=api
    await t.bridge.step(t.now);await t.bridge.step(t.now+1)
    assert methods==['POST','GET']
    with t.bridge.db() as db:assert db.execute("select count(*) from events where state='completed'").fetchone()[0]==1

async def test_same_chat_text_waits_for_its_audio(setup):
    t=setup
    with t.bridge.db() as db:
        rows=db.execute('select id,payload from events').fetchall()
        for row in rows:
            value=json.loads(row['payload']);value['media_status']='pending'
            db.execute('update events set payload=? where id=?',(json.dumps(value),row['id']))
    t.receive('new-text')
    async def forbidden(*args):pytest.fail('must keep same chat order')
    t.bridge.openbot=forbidden
    await t.bridge.step(t.now)


def test_expired_photos_are_removed_only_by_owned_filename(tmp_path):
    import os
    from aguaviva.attendance_media import cleanup
    photo=tmp_path/('a'*64+'.jpg');photo.write_bytes(b'x')
    unrelated=tmp_path/'keep.jpg';unrelated.write_bytes(b'x')
    for path in [photo,unrelated]:os.utime(path,(1,1))
    cleanup(tmp_path)
    assert not photo.exists() and unrelated.exists()

async def test_serial_context_reset_precedes_message_and_duplicate_has_no_reset(tmp_path):
    from aguaviva.connector import SerialSession
    for name,value in [('url','http://127.0.0.1:1234'),('token','t'*40)]:
        p=tmp_path/name;p.write_text(value);p.chmod(0o600)
    calls=[]
    def upstream(r):
        calls.append((r.method,r.url.path))
        if r.url.path.endswith('context/clear'):return httpx.Response(200,json={'ok':True})
        if r.method=='GET':return httpx.Response(200,json={'status':'completed'})
        return httpx.Response(202,json={'deliveries':[{'id':'delivery-test','recipientAgentId':'agent-test'}]})
    state=SerialSession('agent-test',tmp_path,tmp_path/'connector.sqlite',httpx.MockTransport(upstream))
    for ident in ['job-a','job-a','job-b']:
        result=await state.submit({'text':'data for '+ident,'clientMessageId':ident});assert result.status_code==202
    assert calls==[('POST','/v1/agents/agent-test/context/clear'),('POST','/v1/agents/agent-test/messages'),('GET','/v1/agents/agent-test/deliveries/delivery-test'),('POST','/v1/agents/agent-test/context/clear'),('POST','/v1/agents/agent-test/messages')]

async def test_serial_context_refuses_to_reset_running_turn(tmp_path):
    from aguaviva.connector import SerialSession
    for name,value in [('url','http://127.0.0.1:1234'),('token','t'*40)]:
        p=tmp_path/name;p.write_text(value);p.chmod(0o600)
    calls=[]
    def upstream(r):
        calls.append(r.url.path)
        if r.method=='GET':return httpx.Response(200,json={'status':'running'})
        return httpx.Response(200,json={'ok':True}) if r.url.path.endswith('clear') else httpx.Response(202,json={'deliveries':[{'id':'delivery','recipientAgentId':'agent-test'}]})
    state=SerialSession('agent-test',tmp_path,tmp_path/'connector.sqlite',httpx.MockTransport(upstream))
    await state.submit({'text':'A','clientMessageId':'a'})
    assert (await state.submit({'text':'B','clientMessageId':'b'})).status_code==429
    assert len([p for p in calls if p.endswith('clear')])==1

async def test_serial_crash_uncertainty_survives_restart(tmp_path):
    from aguaviva.connector import SerialSession
    for name,value in [('url','http://127.0.0.1:1234'),('token','t'*40)]:
        p=tmp_path/name;p.write_text(value);p.chmod(0o600)
    def upstream(r):
        if r.url.path.endswith('clear'):return httpx.Response(200,json={'ok':True})
        raise httpx.ReadTimeout('ambiguous')
    state=SerialSession('agent-test',tmp_path,tmp_path/'connector.sqlite',httpx.MockTransport(upstream))
    assert (await state.submit({'text':'A','clientMessageId':'a'})).status_code==503
    restarted=SerialSession('agent-test',tmp_path,tmp_path/'connector.sqlite',httpx.MockTransport(lambda r:pytest.fail('must not replay')))
    assert (await restarted.submit({'text':'B','clientMessageId':'b'})).status_code==503

async def test_media_endpoint_authentication_and_bound_path(setup):
    t=setup;key=t.root/'actions';key.write_text('k'*40);key.chmod(0o600)
    cfg=json.loads(t.config.read_text());cfg['action_key_file']=str(key);t.config.write_text(json.dumps(cfg))
    t.bridge.media_dir.mkdir();ident='a'*64;(t.bridge.media_dir/(ident+'.jpg')).write_bytes(b'photo')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app_for(t.bridge)),base_url='http://test') as c:
        assert (await c.get('/media/'+ident)).status_code==401
        assert (await c.get('/media/'+ident,headers={'Authorization':'Bearer '+'k'*40})).content==b'photo'
        assert (await c.get('/media/not-a-hash',headers={'Authorization':'Bearer '+'k'*40})).status_code==400

async def test_old_turn_cannot_answer_newer_pending_event(setup):
    t=setup;t.receive('newest')
    request=action(t);request['event_id']='newest'
    assert (await t.bridge.action(request))['status']=='inactive_event'


def test_earlier_customer_question_survives_context_window(setup):
    t=setup
    with t.bridge.db() as db:
        db.execute("UPDATE transcript SET created=?",(t.now-100,))
        for number in range(12):db.execute('INSERT INTO transcript VALUES(?,?,?,?,?)',('human-'+str(number),'5511111111111@s.whatsapp.net','human','message',t.now+number))
    context=t.bridge.context('5511111111111@s.whatsapp.net',t.now)
    assert len(context['history'])==8
    assert context['earlier_history'][0]['content']=='quero quentinha'

async def test_structured_reply_is_guarded_and_idempotent(setup):
    t=setup;cfg=json.loads(t.config.read_text());cfg['reply_mode']='actions';t.config.write_text(json.dumps(cfg))
    calls=[]
    async def send(body):calls.append(body);return SimpleNamespace(is_error=False,data={},content=[])
    t.bridge.call_mcp=send
    payload={'chat_jid':'5511111111111@s.whatsapp.net','message_id':'incoming'}
    answer=json.dumps({'actions':[{'operation':'text','body':{'Body':'Olá'}}]})
    await t.bridge.on_finished(payload,answer);await t.bridge.on_finished(payload,answer)
    assert len([c for c in calls if c['path_template']=='/chat/send/text'])==1
    t.receive('human',True)
    await t.bridge.on_finished(payload,answer)
    assert len([c for c in calls if c['path_template']=='/chat/send/text'])==1

async def test_structured_reply_cannot_choose_destination_or_bad_operation(setup):
    t=setup;cfg=json.loads(t.config.read_text());cfg['reply_mode']='actions';t.config.write_text(json.dumps(cfg))
    payload={'chat_jid':'5511111111111@s.whatsapp.net','message_id':'incoming'}
    for value in [{'actions':[{'operation':'delete','body':{}}]},{'actions':[{'operation':'text','body':{},'chat_jid':'999@lid'}]}]:
        with pytest.raises(ValueError):await t.bridge.on_finished(payload,json.dumps(value))

async def test_media_cancellation_keeps_original_for_restart(tmp_path):
    from aguaviva.attendance_media import prepare
    ident='b'*64;source=tmp_path/(ident+'.source');source.write_bytes(b'original')
    request=tmp_path/(ident+'.request.json');request.write_text('{}')
    entered=asyncio.Event()
    async def download(*args):entered.set();await asyncio.Event().wait()
    payload={'kind':'audioMessage','media_id':ident,'media_status':'download_pending'}
    task=asyncio.create_task(prepare(payload,tmp_path,download));await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert source.read_bytes()==b'original' and request.exists()

async def test_action_artifact_is_authenticated_and_confined(tmp_path):
    key=tmp_path/'key';key.write_text('k'*40);key.chmod(0o600)
    directory=tmp_path/'state/results';directory.mkdir(parents=True)
    ident='c'*32;(directory/(ident+'.json')).write_text('{"actions":[]}')
    app=connector_app('agent-test',tmp_path,key,state_dir=tmp_path/'state')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as c:
        assert (await c.get('/results/'+ident)).status_code==401
        headers={'Authorization':'Bearer '+'k'*40}
        assert (await c.get('/results/'+ident,headers=headers)).json()=={'actions':[]}
        assert (await c.get('/results/not-a-reference',headers=headers)).status_code==400
        (directory/(ident+'.json')).unlink();(directory/(ident+'.json')).symlink_to(key)
        assert (await c.get('/results/'+ident,headers=headers)).status_code==404

async def test_backend_fetches_and_validates_action_artifact(setup,monkeypatch):
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    t=setup;key=t.root/'connector-key';key.write_text('k'*40);key.chmod(0o600)
    cfg=json.loads(t.config.read_text());cfg.update(reply_mode='actions',connector_url='http://127.0.0.1:8091',connector_key_file=str(key));t.config.write_text(json.dumps(cfg))
    async def result(request):
        assert request.headers['authorization']=='Bearer '+'k'*40
        return JSONResponse({'actions':[{'operation':'text','body':{'Body':'Arquivo validado'}}]})
    app=Starlette(routes=[Route('/results/{ident}',result)])
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.ASGITransport(app),**kw))
    calls=[]
    async def send(body):calls.append(body);return SimpleNamespace(is_error=False,data={},content=[])
    t.bridge.call_mcp=send
    await t.bridge.on_finished({'chat_jid':'5511111111111@s.whatsapp.net','message_id':'incoming'},json.dumps({'actions_ref':'d'*32}))
    assert any(call['path_template']=='/chat/send/text' and call['body']['Body']=='Arquivo validado' for call in calls)


def test_carousel_schema_rejects_invented_keys_before_dispatch():
    from aguaviva.result import validate_actions
    card={'Body':'Produto real','Image':'data:image/jpeg;base64,image','Buttons':[{'type':'cta_url','title':'Ver e pedir','url':'https://example.com/product'}]}
    valid={'actions':[{'operation':'carousel','body':{'Body':'Disponíveis agora','Cards':[card,card]}}]}
    validate_actions(valid)
    card['Title']='not in active schema'
    with pytest.raises(ValueError,match='Additional properties'):validate_actions(valid)
