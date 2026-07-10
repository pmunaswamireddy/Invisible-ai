import codecs

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

text = text.replace('def _get_ghost_target(self):', '    def _get_ghost_target(self):')

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Indentation fixed successfully.")
