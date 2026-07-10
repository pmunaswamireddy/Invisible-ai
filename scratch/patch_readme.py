import codecs

path = 'd:/invisibleai/README.md'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

new_table = """| Hotkey | Action |
| :--- | :--- |
| **`Esc`** | Deactivate Command Mode |
| **`Space`** / **`H`** | Toggle visibility (minimize/dock or restore) |
| **`K`** kkk/ **`E`** | Toggle Ghost Typing / Typist Mode (Types seamlessly in background!) |
| **`B`** / **`W`** | Open / Close Internal Stealth Browser |
| **`F`** | Toggle Background Focus Mode (Unclickable overlay) |
| **`P`** | Rotate AI Provider (Gemini -> Groq -> OpenRouter -> NVIDIA) |
| **`S`** | Scan Screen -> send to Gemini Vision |
| **`I`** | Inject latest AI code block via hardware keystrokes |
| **`1-9`** | Inject specific indexed code block |
| **`D`** | Send Chat Message |
| **`C`** | Clear chat history |
| **`T`** | Toggle Light / Dark Theme |
| **`U`** | Single Voice Input |
| **`M`** | Toggle Continuous Dictation Mode |
| **`V`** | Toggle Speaker TTS Mute / Unmute |
| **`O`** | Rotate TTS Voice Model |
| **`L`** | Launch / Stop Live Interview Mode |
| **`X`** | Force Exit |
| **`⬆ / ⬇ / ⬅ / ➡`** | Reposition Overlay by 20px |
"""

# Extract the old table
import re
table_regex = r"\| Hotkey \| Action \|.*?\| \*\*`.*?Reposition Overlay by 20px \|"
text = re.sub(table_regex, new_table, text, flags=re.DOTALL)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("README updated")
