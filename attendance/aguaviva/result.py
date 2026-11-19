"""Stage an agent-generated action payload without copying media through model output."""
import json
import os
from pathlib import Path
import secrets
import sys
from jsonschema import Draft7Validator, ValidationError

SCHEMAS=json.loads(Path(__file__).with_name("schemas.json").read_text())
CAROUSEL=Draft7Validator({"$ref":"#/definitions/MessageCarousel","definitions":SCHEMAS})

def validate_actions(value):
    if not isinstance(value,dict) or set(value)!={"actions"} or not isinstance(value["actions"],list) or len(value["actions"])>10:raise ValueError("actions required")
    for action in value["actions"]:
        if not isinstance(action,dict) or set(action)!={"operation","body"} or action["operation"] not in {"text","buttons","carousel","react","handoff"} or not isinstance(action["body"],dict):raise ValueError("invalid action")
        if action["operation"]=="carousel":
            try:CAROUSEL.validate({**action["body"],"Phone":"validated-by-backend"})
            except ValidationError as error:raise ValueError(error.message) from None



def main():
    value=json.load(sys.stdin)
    validate_actions(value)
    directory=Path(os.environ['ATTENDANCE_RESULTS_DIR']);directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    ident=secrets.token_hex(16);path=directory/(ident+'.json')
    raw=json.dumps(value,ensure_ascii=False).encode()
    if len(raw)>4*1024*1024:raise ValueError('result too large')
    with path.open('xb') as out:
        path.chmod(0o600);out.write(raw)
    print(json.dumps({'actions_ref':ident}))

if __name__=='__main__':main()
