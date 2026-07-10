import codecs

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

text = text.replace('class KeyBdInput(ctypes.Structure):', 'PUL = ctypes.POINTER(ctypes.c_ulong)\n\nclass KeyBdInput(ctypes.Structure):')

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("PUL restored.")
