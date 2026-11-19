"""Offline portable snapshot: never opens the application against the source DB."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
from contextlib import contextmanager

@contextmanager
def exclusive(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    with (directory/'.attendance.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def snapshot(source,destination):
    source=Path(source);destination=Path(destination)
    with exclusive(source):
        destination.mkdir(mode=0o700,parents=True,exist_ok=False)
        with sqlite3.connect('file:'+str(source/'bridge.sqlite')+'?mode=ro',uri=True) as src:
            with sqlite3.connect(destination/'bridge.sqlite') as dst:src.backup(dst)
        media=source/'media-inbox'
        if media.exists():
            (destination/'media-inbox').mkdir(mode=0o700)
            for item in media.iterdir():
                if item.is_file() and not item.is_symlink() and re.fullmatch(r'[a-f0-9]{64}\.(source|jpg|request\.json)',item.name):
                    shutil.copyfile(item,destination/'media-inbox'/item.name)
        hashes={}
        for file in destination.rglob('*'):
            if file.is_file():
                file.chmod(0o600);hashes[str(file.relative_to(destination))]=hashlib.sha256(file.read_bytes()).hexdigest()
        manifest=destination/'manifest.json';manifest.write_text(json.dumps({'version':1,'files':hashes},indent=2));manifest.chmod(0o600)


def restore(source,destination):
    source=Path(source);destination=Path(destination)
    manifest=json.loads((source/'manifest.json').read_text())
    if manifest['version']!=1:raise ValueError('unsupported backup')
    for name,digest in manifest['files'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('invalid backup path')
        file=source/name
        if file.is_symlink() or source.resolve() not in file.resolve().parents or hashlib.sha256(file.read_bytes()).hexdigest()!=digest:
            raise ValueError('invalid backup')
    destination.mkdir(parents=True,mode=0o700,exist_ok=False)
    for name in manifest['files']:
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        shutil.copyfile(source/name,target);target.chmod(0o600)
    with sqlite3.connect(destination/'bridge.sqlite') as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('database integrity')
        # Local media paths are materialized for this installation, never copied as host contracts.
        for table,column in [('events','payload'),('activity','latest')]:
            for rowid,raw in db.execute(f'SELECT rowid,{column} FROM {table}').fetchall():
                if not raw:continue
                value=json.loads(raw)
                if value.get('media_path'):
                    ident=value.get('media_id','')
                    if not re.fullmatch('[a-f0-9]{64}',ident):raise ValueError('invalid media id')
                    value['media_path']=str((destination/'media-inbox'/(ident+'.jpg')).resolve())
                    db.execute(f'UPDATE {table} SET {column}=? WHERE rowid=?',(json.dumps(value),rowid))


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['snapshot','restore'])
    parser.add_argument('source');parser.add_argument('destination');args=parser.parse_args()
    (snapshot if args.operation=='snapshot' else restore)(args.source,args.destination)
    print('ok')

if __name__=='__main__':main()
