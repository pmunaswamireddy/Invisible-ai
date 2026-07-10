import codecs
import re
path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# Fix the delay keyword argument
text = text.replace('delay=0.003)', 'base_delay=0.003)')

# Safely inject _global_http_session near the top imports
session_decl = '''import requests

# Global HTTP Session for Connection Pooling (Hyperfast UI Latency)
_global_http_session = requests.Session()
'''
if '_global_http_session = requests.Session()' not in text:
    # Find first import to inject safely
    text = re.sub(r'import queue', 'import queue\n' + session_decl, text, count=1)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Errors fixed successfully.")
