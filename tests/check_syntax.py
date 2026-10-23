#!/usr/bin/env python3
import ast
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
for p in ROOT.rglob('*'):
    if not p.is_file() or any(part in ('.git','.venv','outputs','target','__pycache__') for part in p.parts):
        continue
    try: source=p.read_text()
    except UnicodeDecodeError: continue
    if p.suffix=='.json': json.loads(source)
    if p.suffix=='.py' or (source.startswith('#!') and 'python' in source.splitlines()[0]):
        ast.parse(source,filename=str(p))
    if source.startswith('#!') and any(s in source.splitlines()[0] for s in ('bash','/sh')):
        subprocess.run(['bash','-n',str(p)],check=True)
print('Python, JSON and shell syntax: OK')
