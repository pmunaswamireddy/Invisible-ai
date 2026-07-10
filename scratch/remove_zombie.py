import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# Remove the zombie killer block! It's causing immediate exits!
zombie_block = r'    # --- KILL ZOMBIE PROCESSES TO RELEASE GLOBAL HOTKEYS ---.*?    except:\s*pass'
text = re.sub(zombie_block, '    pass', text, flags=re.DOTALL)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Zombie killer removed")
