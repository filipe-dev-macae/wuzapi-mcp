"""Dedicated serial OpenBot adapter with durable dispatch receipts and clean contexts."""
import argparse
import asyncio
import hashlib
import hmac
import json
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx2 as httpx
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response, FileResponse
from starlette.routing import Route
from .bridge import private_text


def endpoint(value):
    url=urlsplit(value)
    if (url.scheme not in {'http','https'} or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in {'','/'}):raise ValueError('invalid endpoint')
    if url.scheme=='http' and url.hostname not in {'127.0.0.1','localhost','connector'}:raise ValueError('remote endpoint requires TLS')
    return value.rstrip('/')


async def remote_request(config,method,path,body,transport=None):
    async with httpx.AsyncClient(timeout=35,trust_env=False,follow_redirects=False,transport=transport) as client:
        return await client.post(endpoint(config['connector_url'])+'/invoke',json={'method':method,'path':path,'body':body},
            headers={'Authorization':'Bearer '+private_text(Path(config['connector_key_file']))})


class SerialSession:
    def __init__(self,agent,directory,database,transport=None):
        self.agent=agent;self.directory=Path(directory);self.database=Path(database);self.transport=transport
        self.lock=asyncio.Lock()
        self.database.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,digest TEXT,state TEXT,receipt TEXT,created REAL)')
            db.execute("UPDATE jobs SET state='uncertain' WHERE state IN ('preparing','submitting')")
        self.database.chmod(0o600)
    def db(self):return sqlite3.connect(self.database)
    async def call(self,method,path,body=None):
        origin=endpoint(private_text(self.directory/'url'))
        if urlsplit(origin).hostname!='127.0.0.1':raise ValueError('local OpenBot required')
        token=private_text(self.directory/'token')
        if len(token)<32:raise ValueError('invalid token')
        async with httpx.AsyncClient(timeout=25,trust_env=False,follow_redirects=False,transport=self.transport) as client:
            return await client.request(method,origin+path,json=body,headers={'Authorization':'Bearer '+token})
    async def submit(self,body):
        ident=body['clientMessageId'];digest=hashlib.sha256(body['text'].encode()).hexdigest()
        prefix='/v1/agents/'+self.agent
        async with self.lock:
            with self.db() as db:
                prior=db.execute('SELECT digest,state,receipt FROM jobs WHERE id=?',(ident,)).fetchone()
                active=db.execute("SELECT id,state,receipt FROM jobs WHERE state IN ('submitted','uncertain')").fetchall()
            if prior:
                if prior[0]!=digest:return JSONResponse({'error':'id reused'},409)
                if prior[2]:return JSONResponse(json.loads(prior[2]),202)
                if prior[1]!='retry':return JSONResponse({'error':'dispatch uncertain'},503)
            for job,state,receipt in active:
                if state=='uncertain':return JSONResponse({'error':'unreconciled execution'},503)
                delivery=json.loads(receipt)['deliveries'][0]['id']
                response=await self.call('GET',prefix+'/deliveries/'+delivery)
                if response.status_code!=200 or response.json().get('status') not in {'completed','failed','interrupted','cancelled'}:
                    return JSONResponse({'error':'agent busy'},429)
                with self.db() as db:db.execute("UPDATE jobs SET state='completed' WHERE id=?",(job,))
            with self.db() as db:
                db.execute("INSERT INTO jobs VALUES(?,?,'preparing',NULL,?) ON CONFLICT(id) DO UPDATE SET state='preparing'",(ident,digest,time.time()))
            try:
                # shortcut: one dedicated serial agent, use native per-chat sessions when supported.
                cleared=await self.call('POST',prefix+'/context/clear')
                if cleared.status_code!=200:
                    with self.db() as db:db.execute("UPDATE jobs SET state='retry' WHERE id=?",(ident,))
                    return JSONResponse({'error':'context busy or unavailable'},429 if cleared.status_code==409 else 503)
                with self.db() as db:db.execute("UPDATE jobs SET state='submitting' WHERE id=?",(ident,))
                result=await self.call('POST',prefix+'/messages',body)
                if result.status_code!=202:
                    with self.db() as db:db.execute("UPDATE jobs SET state=? WHERE id=?",('retry' if result.status_code in {401,403,429} else 'uncertain',ident))
                    return Response(result.content,status_code=result.status_code,media_type='application/json')
                receipt=result.json();deliveries=receipt['deliveries']
                if len(deliveries)!=1 or deliveries[0]['recipientAgentId']!=self.agent or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',deliveries[0]['id']):
                    raise ValueError('invalid receipt')
                with self.db() as db:db.execute("UPDATE jobs SET state='submitted',receipt=? WHERE id=?",(json.dumps(receipt),ident))
                return JSONResponse(receipt,202)
            except (OSError,ValueError,KeyError,TypeError,httpx.HTTPError):
                with self.db() as db:db.execute("UPDATE jobs SET state='uncertain' WHERE id=?",(ident,))
                return JSONResponse({'error':'dispatch uncertain'},503)


def app_for(agent_id,automation_dir,key_file,transport=None,*,state_dir=None,backend_url=None,backend_key_file=None,media_dir=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',agent_id):raise ValueError('invalid agent')
    session=SerialSession(agent_id,automation_dir,Path(state_dir)/'sessions.sqlite',transport) if state_dir else None
    async def invoke(request):
        key=private_text(Path(key_file))
        if len(key)<32 or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+key):return JSONResponse({'error':'unauthorized'},401)
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>32768:return JSONResponse({'error':'too large'},413)
        try:
            value=json.loads(raw);path=value['path'];method=value['method'];body=value.get('body');prefix='/v1/agents/'+agent_id
            valid=(method=='POST' and path==prefix+'/messages' and isinstance(body,dict)
                and set(body)=={'text','clientMessageId'} and isinstance(body['text'],str) and 0<len(body['text'])<30000
                and isinstance(body['clientMessageId'],str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',body['clientMessageId']))
            if valid:
                if session is None:return JSONResponse({'error':'serial session storage required'},503)
                return await session.submit(body)
            valid=method=='GET' and body is None and (path==prefix+'/pending' or re.fullmatch(re.escape(prefix)+r'/deliveries/[A-Za-z0-9_-]{1,128}',path))
            if not valid:return JSONResponse({'error':'operation not allowed'},403)
            local=session or SerialSession(agent_id,automation_dir,Path(key_file).parent/'read-sessions.sqlite',transport)
            result=await local.call(method,path)
            return Response(result.content,status_code=result.status_code,media_type='application/json')
        except (ValueError,KeyError,TypeError):return JSONResponse({'error':'invalid request'},400)
        except (OSError,httpx.HTTPError):return JSONResponse({'error':'upstream uncertain'},502)
    async def status(request):
        key=private_text(Path(key_file))
        if not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+key):return JSONResponse({'error':'unauthorized'},401)
        return JSONResponse({'mode':'dedicated_serial_reset','persistent':session is not None})
    async def image(request):
        key=private_text(Path(backend_key_file)) if backend_key_file else ''
        if not key or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+key):return JSONResponse({'error':'unauthorized'},401)
        ident=request.path_params['ident']
        if not re.fullmatch('[a-f0-9]{64}',ident) or not backend_url or not media_dir:return JSONResponse({'error':'invalid media'},400)
        async with httpx.AsyncClient(timeout=30,trust_env=False,follow_redirects=False) as client:
            async with client.stream('GET',endpoint(backend_url)+'/media/'+ident,headers={'Authorization':'Bearer '+key}) as response:
                if response.status_code!=200:return JSONResponse({'error':'media unavailable'},404)
                content=bytearray()
                async for part in response.aiter_bytes():
                    content.extend(part)
                    if len(content)>12*1024*1024:return JSONResponse({'error':'media too large'},413)
        from PIL import Image
        import io
        Image.MAX_IMAGE_PIXELS=20_000_000
        with Image.open(io.BytesIO(content)) as picture:picture.verify()
        directory=Path(media_dir);directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        from .attendance_media import cleanup
        cleanup(directory)
        path=directory/(ident+'.jpg');path.write_bytes(content);path.chmod(0o600)
        return JSONResponse({'media_path':str(path.resolve())})
    async def result_file(request):
        key=private_text(Path(key_file))
        if len(key)<32 or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+key):return JSONResponse({'error':'unauthorized'},401)
        ident=request.path_params['ident']
        if not state_dir or not re.fullmatch('[a-f0-9]{32}',ident):return JSONResponse({'error':'invalid result'},400)
        directory=Path(state_dir)/'results'
        if directory.exists():
            for old in directory.glob('*.json'):
                if not old.is_symlink() and time.time()-old.stat().st_mtime>86400:old.unlink()
        path=directory/(ident+'.json')
        if path.is_symlink() or not path.is_file() or path.stat().st_size>4*1024*1024 or time.time()-path.stat().st_mtime>86400:return JSONResponse({'error':'result unavailable'},404)
        return FileResponse(path,media_type='application/json',headers={'Cache-Control':'no-store'})
    async def health(request):return JSONResponse({'status':'ok'})
    return Starlette(routes=[Route('/results/{ident}',result_file),Route('/invoke',invoke,methods=['POST']),Route('/mode',status),Route('/materialize/{ident}',image,methods=['POST']),Route('/healthz',health)])


def main():
    parser=argparse.ArgumentParser()
    for name in ['agent','automation-dir','key-file','state-dir','backend-url','backend-key-file','media-dir']:parser.add_argument('--'+name,required=True)
    parser.add_argument('--port',type=int,default=8091);args=parser.parse_args()
    from .backup import exclusive
    with exclusive(Path(args.state_dir)):
        uvicorn.run(app_for(args.agent,args.automation_dir,args.key_file,state_dir=args.state_dir,backend_url=args.backend_url,backend_key_file=args.backend_key_file,media_dir=args.media_dir),host='127.0.0.1',port=args.port,access_log=False)

if __name__=='__main__':main()
