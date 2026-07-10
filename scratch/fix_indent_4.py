import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

text = re.sub(r'        except Exception:\s*pass\s*def __init__\(self\):', r'        except Exception:\n            pass\n\n    def __init__(self):', text)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Indentation fixed via regex")
