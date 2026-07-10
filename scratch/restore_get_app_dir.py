import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# Add get_app_dir back to the top of the file after imports
func = """
def get_app_dir():
    import sys, os
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))
"""
text = text.replace('import signal\n', 'import signal\n' + func + '\n')

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Restored get_app_dir.")
