#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import email
import re
import shutil
from email.header import decode_header
from subprocess import run, PIPE
from pathlib import Path
import tempfile

def rollback():
    print("INFO: Rolling back incomplete task/note creation:")
    run(['task', 'rc.confirmation=off', 'undo'], check=False)

home_dir = Path.home()
taskopenrc = home_dir / ".taskopenrc"
notes_folder_pat = re.compile(r"^[^#]*\s*NOTES_FOLDER\s*=\s*(.*)$")
notes_folder = ""

if taskopenrc.exists():
    with taskopenrc.open("r", encoding="utf-8") as f:
        for line in f:
            match = notes_folder_pat.match(line)
            if match:
                notes_folder = match.group(1).strip().strip('"')

if "$HOME" in notes_folder:
    notes_folder = notes_folder.replace("$HOME", str(home_dir))

if not notes_folder:
    notes_folder = str(home_dir / ".tasknotes")

notes_path = Path(notes_folder)
notes_path.mkdir(mode=0o750, exist_ok=True)

message_content = sys.stdin.read()
message = email.message_from_string(message_content)

body = []
html = []

for part in message.walk():
    content_type = part.get_content_type()
    payload = part.get_payload(decode=True)
    if payload:
        charset = part.get_content_charset('utf-8')
        decoded_payload = payload.decode(charset, errors='replace')
        if content_type == "text/plain":
            body.append(decoded_payload)
        elif content_type == "text/html":
            html.append(decoded_payload)

if html:
    with tempfile.NamedTemporaryFile('w+', delete=False, encoding='utf-8') as tmp:
        tmp.write(''.join(html))
        tmp_name = tmp.name

    p1 = run(['cat', tmp_name], stdout=PIPE, check=False)
    p2 = run(['elinks', '--dump'], input=p1.stdout, stdout=PIPE, check=False, text=False)
    out_decoded = p2.stdout.decode('utf-8', errors='replace')
    os.unlink(tmp_name)
else:
    out_decoded = ''.join(body)

with tempfile.NamedTemporaryFile('w+', delete=False, encoding='utf-8') as tmp_final:
    tmp_final.write(out_decoded)
    tmp_final_name = tmp_final.name

subject = message.get('Subject', '')
decoded_subject_parts = decode_header(subject)
decoded_subject = ''.join([
    part.decode(encoding or 'utf-8', errors='replace') if isinstance(part, bytes) else part
    for part, encoding in decoded_subject_parts
])
decoded_subject = decoded_subject or "E-Mail import: no subject specified."
task_description = f"E-Mail subject: {decoded_subject}" if decoded_subject != "E-Mail import: no subject specified." else decoded_subject

res = run(['task', 'add', 'pri:L', '+email', '--', task_description], stdout=PIPE, check=False)
res_text = res.stdout.decode('utf-8')

match = re.match(r"^Created task (\d+)", res_text)
if match:
    print(match.group(0).strip())
    task_id = match.group(1)
    uuid_res = run(['task', task_id, 'uuids'], stdout=PIPE, check=False)
    uuid = uuid_res.stdout.decode('utf-8').strip()
    ret = run(['task', task_id, 'annotate', '--', 'email: Notes'], check=False).returncode
    if ret:
        print(f"ERR: Sorry, cannot annotate task with ID={task_id}.")
        rollback()

    notes_file = notes_path / f"{uuid}.txt"
    try:
        shutil.copy(tmp_final_name, notes_file)
        os.remove(tmp_final_name)
    except Exception:
        print(f"ERR: Sorry, cannot create notes file \"{notes_file}\".")
        rollback()

### EOF
