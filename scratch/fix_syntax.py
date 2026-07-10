import codecs

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

bad_string = "f'wmic process where \"name='python.exe' and commandline like '%overlay.py%' and ProcessId!={my_pid}\" delete'"
good_string = 'f\'wmic process where "name=\\\'python.exe\\\' and commandline like \\\'%overlay.py%\\\' and ProcessId!={my_pid}" delete\''

text = text.replace(bad_string, good_string)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Syntax fixed")
