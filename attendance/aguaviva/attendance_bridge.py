"""Água Viva event adapter; uses the existing WuzAPI queue and scoped MCP client."""
import asyncio
import base64
from contextlib import asynccontextmanager, suppress
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import os
import time
from urllib.parse import parse_qs

from fastmcp import Client
from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse
from starlette.routing import Route
import uvicorn
from .bridge import Bridge, normalize, settings, private_text

from .attendance_media import capture, prepare, cleanup

class Attendance(Bridge):
    def __init__(self, config_path, database, transport=None):
        super().__init__(config_path, database, transport)
        self.lock = asyncio.Lock()
        self.media_dir = Path(database).parent / "media-inbox"
        self.send_locks = {}
        self.mcp = None
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS activity(chat TEXT PRIMARY KEY, human_until REAL NOT NULL DEFAULT 0, latest TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS outgoing(id TEXT PRIMARY KEY, chat TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS effects(id TEXT PRIMARY KEY, operation TEXT NOT NULL, card_count INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS action_payload(id TEXT PRIMARY KEY, digest TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS transcript(id TEXT PRIMARY KEY, chat TEXT NOT NULL, direction TEXT NOT NULL, content TEXT NOT NULL, created REAL NOT NULL)')

    def receive(self, raw, content_type, now):
        config = settings(self.config_path)
        if content_type == 'application/x-www-form-urlencoded':
            form = parse_qs(raw.decode(), strict_parsing=True)
            value = json.loads(form['jsonData'][0]); value['userID'] = form['userID'][0]
        else:
            value = json.loads(raw)
        info = value.get('event', {}).get('Info', {})
        if info.get('Chat') in config.get('chat_aliases',{}):
            info['Chat']=config['chat_aliases'][info['Chat']]
        own = info.get('IsFromMe')
        if type(own) is not bool:
            return False
        info['IsFromMe'] = False
        item = normalize(json.dumps(value).encode(), 'application/json', config, now)
        if not item:
            return False
        key, payload = item
        payload['sender_name']=str(info.get('PushName',''))[:200]
        payload['sender_alt']=str(info.get('SenderAlt',''))[:100]
        chat, ident = payload['chat_jid'], payload['message_id']
        if chat in config.get('excluded_chats', []):
            return False
        with self.db() as db:
            if db.execute('SELECT 1 FROM transcript WHERE id=?', (key,)).fetchone():
                return False
            is_bot = bool(db.execute('SELECT 1 FROM outgoing WHERE id=? AND chat=?', (ident,chat)).fetchone())
            direction = 'bot' if own and is_bot else 'human' if own else 'customer'
            if direction == 'customer': capture(value,payload,key,self.media_dir)
            db.execute('INSERT INTO transcript VALUES(?,?,?,?,?)', (key,chat,direction,payload['text'][:2000],now))
            db.execute('INSERT OR IGNORE INTO activity(chat) VALUES(?)', (chat,))
            if direction == 'customer':
                db.execute('UPDATE activity SET latest=? WHERE chat=?', (json.dumps(payload),chat))
                for queued in db.execute("SELECT id,payload FROM events WHERE state IN ('pending','human_paused')").fetchall():
                    prior=json.loads(queued['payload'])
                    if prior['chat_jid']==chat and prior.get('recheck_after_human'):
                        db.execute("UPDATE events SET state='superseded',updated=? WHERE id=?",(now,queued['id']))
            if direction == 'human':
                stamp = __import__('datetime').datetime.fromisoformat(payload['timestamp']).timestamp()
                db.execute('UPDATE activity SET human_until=MAX(human_until,?) WHERE chat=?', (stamp+300,chat))
                row = db.execute('SELECT latest FROM activity WHERE chat=?',(chat,)).fetchone()
                if row['latest']:
                    pending = [r for r in db.execute("SELECT id,payload FROM events WHERE state IN ('pending','human_paused')") if json.loads(r['payload'])['chat_jid']==chat]
                    for entry in pending:
                        db.execute('UPDATE events SET created=?,updated=? WHERE id=?',(now,now,entry['id']))
                    if not pending:
                        prior = json.loads(row['latest']); prior['recheck_after_human'] = True
                        recheck = 'human-'+key
                        db.execute("INSERT INTO events(id,payload,state,created,updated) VALUES(?,?,'pending',?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,state='pending',created=excluded.created,updated=excluded.updated WHERE events.state IN ('completed','failed','held')",(recheck,json.dumps(prior),now,now))
            # Ingestion and queue insert commit together: no lost event after a crash.
            if not own:
                db.execute('INSERT OR IGNORE INTO events(id,payload,created,updated) VALUES(?,?,?,?)',(key,json.dumps(payload,ensure_ascii=False),now,now))
        return True

    def context(self, chat, now):
        with self.db() as db:
            row = db.execute('SELECT human_until FROM activity WHERE chat=?',(chat,)).fetchone()
            history = [dict(r) for r in db.execute('SELECT direction,content,created FROM transcript WHERE chat=? ORDER BY created DESC LIMIT 8',(chat,))][::-1]
            # Keep earlier requests retrievable after a context reset; do not silently lose an open question.
            cutoff=history[0]['created'] if history else now
            earlier=[dict(r) for r in db.execute("SELECT direction,content,created FROM transcript WHERE chat=? AND created<? ORDER BY created",(chat,cutoff))]
        return {'human_until': row['human_until'] if row else 0, 'now':now,'history':history,'earlier_history':earlier}

    async def on_submitted(self, payload):
        for operation,body in [('read',{'Id':[payload['message_id']],'SenderPhone':payload['chat_jid']}),('presence',{'State':'composing'})]:
            await self.action({'chat_jid':payload['chat_jid'],'event_id':payload['message_id'],'action_id':'backend-'+operation,'operation':operation,'body':body})

    async def on_finished(self, payload, answer=None):
        try:
            if settings(self.config_path).get('reply_mode')=='actions' and answer is not None:
                value=json.loads(answer)
                if isinstance(value,dict) and set(value)=={'actions_ref'}:
                    ident=value['actions_ref']
                    if not isinstance(ident,str) or not __import__('re').fullmatch('[a-f0-9]{32}',ident):raise ValueError('invalid result reference')
                    from .connector import endpoint
                    import httpx2 as httpx
                    config=settings(self.config_path)
                    async with httpx.AsyncClient(timeout=25,trust_env=False,follow_redirects=False) as client:
                        async with client.stream('GET',endpoint(config['connector_url'])+'/results/'+ident,headers={'Authorization':'Bearer '+private_text(Path(config['connector_key_file']))}) as response:
                            if response.status_code!=200:raise ValueError('result unavailable')
                            raw=bytearray()
                            async for part in response.aiter_bytes():
                                raw.extend(part)
                                if len(raw)>4*1024*1024:raise ValueError('result too large')
                    value=json.loads(raw)
                from .result import validate_actions
                validate_actions(value)
                for index,action in enumerate(value['actions']):
                    request={'chat_jid':payload['chat_jid'],'event_id':payload['message_id'],'action_id':'result-'+str(index),**action}
                    if action['operation']=='handoff':
                        request.update(operation='text',chat_jid=settings(self.config_path)['manager_jid'],source_chat=payload['chat_jid'])
                    result=await self.action(request)
                    if result['status'] in {'human_paused','stale_event','inactive_event'}:break
                    if result['status']=='outside_online_hours':
                        if action['operation']=='handoff':raise ValueError('handoff not accepted')
                        await self.action({'chat_jid':payload['chat_jid'],'event_id':payload['message_id'],'action_id':'outside-hours','operation':'text','body':{'Body':'Os pedidos online estão fechados neste horário.'}})
                        break
                    if result['status']!='accepted':
                        raise ValueError('guarded action not accepted')
        finally:
            await self.action({'chat_jid':payload['chat_jid'],'event_id':payload['message_id'],'action_id':'backend-paused','operation':'presence','body':{'State':'paused'}})

    async def call_mcp(self, arguments):
        if self.mcp is None:
            raise RuntimeError("MCP unavailable")
        return await self.mcp.call_tool('api_call', arguments)

    async def download_media(self, kind, body):
        config = settings(self.config_path)
        path = '/chat/downloadaudio' if kind == 'audioMessage' else '/chat/downloadimage'
        result = await self.call_mcp({'method':'POST','path_template':path,'instance_id':config['instance_ids'][0],'body':body,'confirmed':True})
        if result.is_error: raise ValueError('download unavailable')
        value = result.data
        for _ in range(4):
            if isinstance(value,str): value = json.loads(value)
            elif isinstance(value,dict) and 'Data' in value: break
            elif isinstance(value,dict) and 'data' in value: value = value['data']
            else: raise ValueError('invalid download response')
        encoded = value['Data'].split(',',1)[1]
        if len(encoded)>16*1024*1024: raise ValueError('media too large')
        return base64.b64decode(encoded,validate=True)

    async def prepare_media(self, now):
        cleanup(self.media_dir)
        with self.db() as db:
            rows = db.execute("SELECT id,payload FROM events WHERE state='pending' ORDER BY created").fetchall()
        for row in rows:
            payload = json.loads(row['payload'])
            if self.context(payload['chat_jid'],now)['human_until'] > now: continue
            if payload.get('media_status') not in ('pending','download_pending'): continue
            await prepare(payload,self.media_dir,self.download_media)
            with self.db() as db:
                db.execute('UPDATE events SET payload=? WHERE id=?',(json.dumps(payload),row['id']))
                latest = db.execute('SELECT latest FROM activity WHERE chat=?',(payload['chat_jid'],)).fetchone()
                if latest and latest['latest'] and json.loads(latest['latest'])['message_id'] == payload['message_id']:
                    db.execute('UPDATE activity SET latest=? WHERE chat=?',(json.dumps(payload),payload['chat_jid']))
                db.execute('UPDATE transcript SET content=? WHERE id=?',(payload['text'][:2000],payload.get('media_id',row['id'])))

    async def step(self, now=None):
        now = time.time() if now is None else now
        # Delay only the relevant chat. Other chats stay eligible.
        with self.db() as db:
            for row in db.execute("SELECT id,payload,state FROM events WHERE state IN ('pending','human_paused')").fetchall():
                payload = json.loads(row['payload']); ctx = self.context(payload['chat_jid'],now)
                state = 'human_paused' if ctx['human_until'] > now else 'pending'
                payload['attendance_context'] = ctx
                db.execute('UPDATE events SET state=?,payload=? WHERE id=?',(state,json.dumps(payload),row['id']))
        await super().step(now)

    async def action(self, value):
        config = settings(self.config_path)
        chat = value.get('chat_jid','')
        chat = config.get('chat_aliases',{}).get(chat,chat)
        if not __import__('re').fullmatch(r'[0-9]+@(s\.whatsapp\.net|lid)',chat):
            raise ValueError('private chat required')
        if not config['dispatch_enabled'] or not config['policy_approved']:
            raise ValueError('attendance disabled')
        is_manager = chat in {config.get('manager_jid',''),config.get('chat_aliases',{}).get(config.get('manager_jid',''),config.get('manager_jid',''))}
        if is_manager and not config.get('allow_manager',False):
            raise ValueError('manager disabled in test')
        if not is_manager and (chat in config.get('excluded_chats',[]) or (not config['allow_all_private'] and chat not in config['allowed_chats'])):
            raise ValueError('chat not allowed')
        op = value.get('operation'); body = dict(value.get('body',{}))
        if op=='status':
            with self.db() as db:
                row=db.execute('SELECT latest FROM activity WHERE chat=?',(chat,)).fetchone()
            return {'status':'authenticated_local_receiver','test_mode':not config['allow_all_private'],'chat_jid':chat,'latest_incoming':json.loads(row['latest']) if row and row['latest'] else None,**self.context(chat,time.time())}
        event_id = value.get('event_id')
        source_chat = value.get('source_chat',chat) if is_manager else chat
        with self.db() as db:
            incoming = db.execute('SELECT latest FROM activity WHERE chat=?',(source_chat,)).fetchone()
        if not incoming or not incoming['latest'] or json.loads(incoming['latest'])['message_id'] != event_id:
            return {'status':'stale_event'}
        with self.db() as db:
            active=[json.loads(r['payload']) for r in db.execute("SELECT payload FROM events WHERE state='submitted'")]
        if not any(p['chat_jid']==source_chat and p['message_id']==event_id for p in active):
            return {'status':'inactive_event'}
        action_key = value.get('action_id')
        if not isinstance(action_key,str) or not 1 <= len(action_key) <= 128:
            raise ValueError('action_id required')
        allowed = {'text' :'/chat/send/text','carousel':'/chat/send/carousel','read':'/chat/markread','presence':'/chat/presence','react':'/chat/react','buttons':'/chat/send/buttons'}
        if op not in allowed:
            raise ValueError('operation not allowed')
        if is_manager and op != 'text':
            raise ValueError('manager accepts handoff text only')
        if op == 'text' and config.get('require_link_preview', False):
            body['LinkPreview'] = True
        async with self.send_locks.setdefault(chat, asyncio.Lock()):
            with self.db() as db:
                latest = db.execute('SELECT latest FROM activity WHERE chat=?',(source_chat,)).fetchone()
            if not latest or not latest['latest'] or json.loads(latest['latest'])['message_id'] != event_id:
                return {'status':'stale_event'}
            ctx = self.context(source_chat,time.time())
            if ctx['human_until'] > time.time():
                return {'status':'human_paused','until':ctx['human_until']}
            if op in {'carousel','buttons'} or (op=='text' and 'stoqui.shop' in body.get('Body','')):
                from datetime import datetime
                from zoneinfo import ZoneInfo
                local=datetime.now(ZoneInfo('America/Sao_Paulo'))
                if local.weekday()>4 or not 600 <= local.hour*60+local.minute < 900:
                    return {'status':'outside_online_hours'}
            if op in {'text','carousel','buttons'}:
                ident = 'AVBOT'+hashlib.sha256(json.dumps([event_id,chat,action_key]).encode()).hexdigest()[:24].upper()
                body['Id']=ident
                with self.db() as db:
                    digest = hashlib.sha256(json.dumps([op,body],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                    known = db.execute('SELECT digest FROM action_payload WHERE id=?',(ident,)).fetchone()
                    if known and known['digest'] != digest:
                        raise ValueError('action_id reused with different content')
                    prior = db.execute('SELECT state FROM outgoing WHERE id=?',(ident,)).fetchone()
                    if prior:
                        return {'status':prior['state'] if prior['state']=='accepted' else 'uncertain','message_id':ident}
                    db.execute('INSERT INTO outgoing VALUES(?,?,?,?)',(ident,chat,'attempting',time.time()))
                    db.execute('INSERT INTO action_payload VALUES(?,?)',(ident,digest))
                    db.execute('INSERT INTO effects VALUES(?,?,?)',(ident,op,len(body.get('Cards',[]))))
            else:
                ident = None
            if op == 'read':
                body['ChatPhone']=chat
                body['SenderPhone']=chat
                body.pop('Chat',None)
            else:
                body['Phone']=chat
            if op == 'presence' and body.get('State') not in {'composing','paused'}:
                raise ValueError('invalid presence')
            # Scoped read/send credential; no admin authority is used by this adapter.
            try:
                result = await self.call_mcp({'method':'POST','path_template':allowed[op],'instance_id':config['instance_ids'][0],'body':body,'confirmed':True})
            except Exception:
                if ident:
                    with self.db() as db: db.execute("UPDATE outgoing SET state='uncertain' WHERE id=?",(ident,))
                return {'status':'uncertain','message_id':ident}
            if ident:
                with self.db() as db:
                    db.execute('UPDATE outgoing SET state=? WHERE id=?',('uncertain' if result.is_error else 'accepted',ident))
                    if not result.is_error:
                        event_key=hashlib.sha256(json.dumps([config['instance_ids'][0],chat,ident]).encode()).hexdigest()
                        db.execute('INSERT OR IGNORE INTO transcript VALUES(?,?,?,?,?)',(event_key,chat,'bot_accepted',str(body.get('Body',''))[:2000],time.time()))
            return {'status':'uncertain' if result.is_error else 'accepted','message_id':ident,'result':result.data if result.data is not None else str(result.content)}


def app_for(bridge):
    async def webhook(request):
        try:
            config=settings(bridge.config_path); raw=bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw)>24*1024*1024: return JSONResponse({'error':'too large'},413)
            signature=request.headers.get('x-hmac-signature','').removeprefix('sha256=')
            key=private_text(Path(config['hmac_key_file']))
            if len(key)<32: return JSONResponse({'error':'configuration'},503)
            expected=hmac.new(key.encode(),raw,hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature,expected): return JSONResponse({'error':'signature'},401)
            async with bridge.lock:
                accepted=bridge.receive(raw,request.headers.get('content-type','').split(';')[0],time.time())
            return JSONResponse({'status':'accepted' if accepted else 'ignored'})
        except (ValueError,KeyError,TypeError,AttributeError):
            return JSONResponse({'error':'invalid event'},400)
    async def action(request):
        config=settings(bridge.config_path)
        supplied=request.headers.get('authorization','').removeprefix('Bearer ')
        key=private_text(Path(config['action_key_file']))
        if len(key)<32 or not hmac.compare_digest(supplied,key): return JSONResponse({'error':'authorization'},401)
        try:
            raw=bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw)>1024*1024: return JSONResponse({'error':'too large'},413)
            return JSONResponse(await bridge.action(json.loads(raw)))
        except Exception as e:
            # A failed request may have reached WhatsApp. Do not repeat it.
            return JSONResponse({'status':'uncertain','error':type(e).__name__},502)
    async def media(request):
        config=settings(bridge.config_path)
        key=private_text(Path(config['action_key_file']))
        if len(key)<32 or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+key):
            return JSONResponse({'error':'unauthorized'},401)
        ident=request.path_params['ident']
        if not __import__('re').fullmatch('[a-f0-9]{64}',ident):return JSONResponse({'error':'invalid media'},400)
        path=bridge.media_dir/(ident+'.jpg')
        if path.is_symlink() or not path.is_file() or time.time()-path.stat().st_mtime>86400:
            return JSONResponse({'error':'media unavailable'},404)
        return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'no-store'})
    async def health(request): return JSONResponse({'status':'ok'})
    async def worker(media=False):
        while True:
            try:
                if media:
                    if settings(bridge.config_path)['dispatch_enabled']: await bridge.prepare_media(time.time())
                else: await bridge.step()
            except Exception as e: print('adapter step unavailable:',type(e).__name__,flush=True)
            await asyncio.sleep(1)
    @asynccontextmanager
    async def lifespan(app):
        config = settings(bridge.config_path)
        async with Client(config['mcp_url'], auth=private_text(Path(config['mcp_key_file'])), timeout=60) as client:
            await client.call_tool('get_usage_guide',{})
            bridge.mcp = client
            tasks=[asyncio.create_task(worker()),asyncio.create_task(worker(True))]
            try: yield
            finally:
                for task in tasks: task.cancel()
                for task in tasks:
                    with suppress(asyncio.CancelledError): await task
                bridge.mcp = None
                from .attendance_media import POOL
                await asyncio.to_thread(POOL.shutdown,wait=True,cancel_futures=True)
    return Starlette(routes=[Route('/media/{ident}',media),Route('/webhook',webhook,methods=['POST']),Route('/action',action,methods=['POST']),Route('/healthz',health)],lifespan=lifespan)

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--data', required=True)
    args=parser.parse_args()
    os.umask(0o077)
    config=settings(Path(args.config))
    if config['dispatch_enabled'] and not config.get('context_isolation_verified',False):
        raise ValueError('context isolation must be verified before enabling dispatch')
    from .backup import exclusive
    with exclusive(Path(args.data)):
        uvicorn.run(app_for(Attendance(Path(args.config),Path(args.data)/'bridge.sqlite')),host=config.get('bind_host','127.0.0.1'),port=config['listen_port'],access_log=False)

if __name__=='__main__': main()
