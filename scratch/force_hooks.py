import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# Add to __init__
init_pattern = r'(app\._overlay_instance = self\s*)'
if 'install_mouse_hook()' not in text:
    text = re.sub(init_pattern, r'\1self.global_scroll_signal.connect(self.handle_global_scroll)\n        install_mouse_hook()\n        ', text, count=1)

# Add to force_exit
exit_pattern = r'(def force_exit\(self\):\s*)'
if 'uninstall_mouse_hook()' not in text:
    text = re.sub(exit_pattern, r'\1uninstall_mouse_hook()\n        ', text, count=1)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Hooks forced.")
