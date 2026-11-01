import json
from pathlib import Path
from app import DEFAULT, FIELDS

values = {
 'A': [True, True, 5000000, 14, 238000, 12, 25, 10, True, True, True, True],
 'B': [None, True, 5000000, 6, 189500, 10, 25, 5, None, None, None, None],
 'C': [True, True, 5000000, None, 244000, 14, 25, 10, True, True, None, None],
 'D': [True, True, 5000000, 11, 231000, None, 25, 10, True, None, True, None],
 'E': [True, True, 5000000, 8, 242500, 13, 25, 12, True, True, True, True]
}
proposals = [dict(id=k, facts=dict(zip(FIELDS,v)), sources={}, evidence={}, warnings=['Instruction attempt requires human review'] if k=='C' else [], approved=True, failed_documentation=k=='B', review_note='Demonstration of expected review outcome; source evidence not included.') for k,v in values.items()]
Path(__file__).with_name('demo.json').write_text(json.dumps(dict(config=DEFAULT, proposals=proposals, demo=True, actor='', reason=''), indent=2), encoding='utf-8')
