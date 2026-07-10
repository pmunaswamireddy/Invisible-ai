import codecs

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# I removed `import sys` by mistake in the remove_redirect.py.
if 'import sys' not in text:
    text = text.replace('    import os\n    os.environ', '    import os\n    import sys\n    os.environ')
    
# Change != to <> for WQL syntax to be safe
text = text.replace('ProcessId!=', 'ProcessId<>')

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Fixed missing sys import and WQL syntax.")
