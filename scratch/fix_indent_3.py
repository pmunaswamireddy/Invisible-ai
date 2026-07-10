import codecs

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

text = text.replace("        except Exception:\n        pass\n\n    def __init__(self):", "        except Exception:\n            pass\n\n    def __init__(self):")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Indentation fixed")
