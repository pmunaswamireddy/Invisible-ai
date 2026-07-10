import codecs
import re
path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

session_code = '''import requests
import os
import sys

# Global HTTP Session for Connection Pooling (Hyperfast UI Latency)
_global_http_session = requests.Session()
'''
if '_global_http_session' not in text:
    text = text.replace('import requests\n', session_code)
    text = re.sub(r'requests\.post\(', '_global_http_session.post(', text)
    text = re.sub(r'requests\.get\(', '_global_http_session.get(', text)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Patched HTTP sessions successfully.")
