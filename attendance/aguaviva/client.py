"""Agent action client; secrets are read from files, never command arguments."""
import json
import os
from pathlib import Path
import sys
import urllib.request
import urllib.error
from .bridge import private_text
from .connector import endpoint


def main():
    value=json.load(sys.stdin)
    url=endpoint(os.environ['ATTENDANCE_URL'])
    key=private_text(Path(os.environ['ATTENDANCE_KEY_FILE']))
    request=urllib.request.Request(url+'/action',data=json.dumps(value).encode(),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=75) as response: result=json.load(response)
        incoming=result.get('latest_incoming') or {}
        if value.get('operation')=='status' and incoming.get('media_status')=='image_ready':
            connector=endpoint(os.environ['ATTENDANCE_CONNECTOR_URL'])
            media=urllib.request.Request(connector+'/materialize/'+incoming['media_id'],data=b'',headers={'Authorization':'Bearer '+key},method='POST')
            with urllib.request.urlopen(media,timeout=45) as response:incoming['media_path']=json.load(response)['media_path']
        print(json.dumps(result,ensure_ascii=False))
    except urllib.error.HTTPError as error:
        print(error.read().decode());sys.exit(1)
    except (OSError,TimeoutError):
        print(json.dumps({'status':'uncertain'}));sys.exit(1)

if __name__=='__main__':main()
