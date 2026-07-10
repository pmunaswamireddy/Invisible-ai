import codecs

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# Add to __init__
if 'install_mouse_hook()' not in text:
    old_init = "        app._overlay_instance = self\r\n"
    new_init = "        app._overlay_instance = self\r\n        self.global_scroll_signal.connect(self.handle_global_scroll)\r\n        install_mouse_hook()\r\n"
    text = text.replace(old_init, new_init)

# Add to force_exit
if 'uninstall_mouse_hook()' not in text:
    old_exit = "    def force_exit(self):\r\n"
    new_exit = "    def force_exit(self):\r\n        uninstall_mouse_hook()\r\n"
    text = text.replace(old_exit, new_exit)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Hooks injected.")
