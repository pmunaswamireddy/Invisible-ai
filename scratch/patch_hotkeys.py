import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# 1. Update the Command Mode system message
old_msg = 'self.add_system_message("⚡ Command Mode Active (Press Space/H: Hide | S: Scan | I: Inject | 1-9: Indexed | P: Model | O: Voice | U: Voice Typist | M: Live Chat | L: Interview | V: Speaker | E: Focus Chat | Esc/Alt+Z: Exit)")'
new_msg = 'self.add_system_message("⚡ Command Mode Active (Space/H: Hide | S: Scan | I: Inject | 1-9: Index | P: Model | O: Voice | K/E: Ghost Type | U: Voice Typist | M: Live Chat | L: Interview | V: Speaker | C: Clear | B/W: Browser | D: Send | Esc/Alt+Z: Exit)")'
text = text.replace(old_msg, new_msg)

# 2. Update tooltips globally
replacements = {
    '"Toggle Light/Dark Theme (Hotkey: Alt+Z then T)"': '"Toggle Light/Dark Theme (Alt+Z -> T)"',
    '"Toggle keyboard input focus mode (Hotkey: Alt+Z then F)"': '"Toggle keyboard input focus mode (Alt+Z -> F)"',
    '"Clear current chat history (Hotkey: Alt+Z then C)"': '"Clear current chat history (Alt+Z -> C)"',
    '"Minimize overlay to edge (Hotkey: Alt+Z then Space or Alt+Z then H)"': '"Minimize overlay to edge (Alt+Z -> Space/H)"',
    '"Exit application (Hotkey: Alt+Z then X)"': '"Exit application (Alt+Z -> X)"',
    '"Select active AI Provider (Hotkey: Alt+Z then P to rotate)"': '"Select active AI Provider (Alt+Z -> P)"',
    '"Capture screen to Gemini Vision (Hotkey: Alt+Z then S)"': '"Capture screen to Gemini Vision (Alt+Z -> S)"',
    '"Type generated code into active window (Hotkey: Alt+Z then I for latest | Alt+Z then 1..9 for indexed blocks)"': '"Type generated code into active window (Alt+Z -> I or 1..9)"',
    '"Toggle TTS Voice Readback (Hotkey: Alt+Z then V)"': '"Toggle TTS Voice Readback (Alt+Z -> V)"',
    '"Toggle Live Interview Mode (Hotkey: Alt+Z then L)"': '"Toggle Live Interview Mode (Alt+Z -> L)"',
    '"Select TTS voice model (Hotkey: Alt+Z then O to rotate)"': '"Select TTS voice model (Alt+Z -> O)"',
    '"Single Voice Input (Types into chat box) (Hotkey: Alt+Z then U)"': '"Single Voice Input (Types into chat box) (Alt+Z -> U)"',
    '"Continuous Live Voice Chat (Hotkey: Alt+Z then M)"': '"Continuous Live Voice Chat (Alt+Z -> M)"',
    '"Send Message (Hotkey: Alt+Z then D)"': '"Send Message (Alt+Z -> D)"'
}

for old, new in replacements.items():
    text = text.replace(old, new)

# 3. Add single instance / zombie killer directly in application main block
zombie_killer = '''if __name__ == "__main__":
    # --- KILL ZOMBIE PROCESSES TO RELEASE GLOBAL HOTKEYS ---
    import os, subprocess, ctypes
    my_pid = str(os.getpid())
    # Kill any other python.exe that is running overlay.py to free up our global hotkeys (Alt+Z, Alt+L)
    try:
        subprocess.call(f'wmic process where "name=\'python.exe\' and commandline like \'%overlay.py%\' and ProcessId!={my_pid}" delete', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass
'''
if '# --- KILL ZOMBIE' not in text:
    text = text.replace('if __name__ == "__main__":', zombie_killer)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Hotkeys and Zombie Killer patched successfully.")
