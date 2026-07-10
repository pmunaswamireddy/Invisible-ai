import re
with open("overlay.py", "r", encoding="utf-8") as f:
    lines = f.readlines()
with open("hotkey_out.txt", "w", encoding="utf-8") as out:
    for i, line in enumerate(lines):
        if "RegisterHotKey" in line:
            out.write(f"L{i+1}: {line.strip()}\n")
        if "hotkey_signal" in line:
            out.write(f"L{i+1}: {line.strip()}\n")
