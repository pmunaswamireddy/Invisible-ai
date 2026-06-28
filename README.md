# Invisible AI Overlay

A highly stealthy, ultra-lightweight, floating AI assistant that sits completely invisibly on your Windows desktop. Built for maximum privacy, latency-free operation, and advanced hardware-level interaction.

---

## 🌟 Key Features

### 1. 🔒 Strict Stealth Mode (Zero Detection)
- **Anti-Screen Capture:** Invisible to screen capture software, recorders, and screenshots (OBS, Discord, Proctoring tools) using the native Windows API `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`.
- **Bypassed Focus Triggers:** Runs with `WS_EX_NOACTIVATE` so clicking the interface never steals focus from the foreground browser window (the browser stays active).
- **Stealth Clicks (WM_MOUSELEAVE Bypass):** Unlike standard overlays that toggle focus on hover (triggering mouse-leave events on the active window), this overlay remains `WS_EX_TRANSPARENT` constantly. Clicks on the overlay are intercepted at the hardware level using `WH_MOUSE_LL` hooks, blocked from the OS, and routed directly to the overlay's widgets. **The browser never knows you clicked outside.**
- **Hotkey Repositioning:** Silently move the overlay using keyboard shortcut chords. This avoids moving the mouse to the overlay, which could leave a trail or trigger mouse-out alerts.

### 2. ⚡ Latency & CPU Optimization
- **Zero Polling Lag:** The heavy 50Hz timer that polled window styles has been completely removed. Hit-testing is now calculated on-demand upon hardware input, dropping CPU usage to 0%.
- **Decompressed Execution:** Startup time is reduced by over 50% (~0.9s load time) by disabling runtime UPX decompression.
- **Level-2 Bytecode Optimization:** Compiled with `-OO` flags to strip debug code, docstrings, and assertions for a lightweight runtime footprint.
- **Deferred Imports:** Large libraries (such as `mss` for screen capture) are deferred to import only when triggered, minimizing initial memory allocation.

### 3. 🛠️ Power User Tools
- **Ghost Typing / Typist Mode:** Simulates hardware keyboard presses (`SendInput`) to type AI responses into target editors character-by-character to bypass clipboard monitors.
- **Vision Screen Scanning:** Instantly crop and scan the overlay's bounds, feeding screenshot snippets directly to the AI model.
- **PowerShell-based TTS:** Speaks responses using Windows SAPI via PowerShell subprocesses, avoiding heavy third-party speech libraries.

---

## 🎹 Keyboard Shortcuts & Chord Mode

Press the leader chord **`Alt + Z`** to activate **Command Mode**, followed by one of the keys below:

| Hotkey | Action |
| :--- | :--- |
| **`Esc`** | Deactivate Command Mode |
| **`Space`** or **`H`** | Toggle visibility (dock to edge) |
| **`K`** | Toggle Ghost Typing / Typist Mode |
| **`P`** | Rotate AI Model / Provider (Gemini ⇄ Groq ⇄ OpenRouter) |
| **`S`** | Scan Screen |
| **`I`** | Inject latest AI code block |
| **`1-9`** | Inject specific indexed code block (Top row or Numpad) |
| **`D`** | Send Chat Message |
| **`C`** | Clear current chat history |
| **`T`** | Toggle Light / Dark Theme |
| **`U`** | Single Voice Input (Listen once and type to chat box) |
| **`M`** | Toggle Continuous Dictation Mode |
| **`V`** | Toggle Speaker TTS Mute / Unmute |
| **`O`** | Rotate TTS Voice Model |
| **`X`** | Force Exit Application |
| **`▲ / ▼ / ◀ / ▶`** | **Reposition Overlay:** Move window by 20px (stays in Command Mode for repeated adjustments) |

---

## 💡 Pro Tips & Anti-Detection Guidelines

> [!WARNING]
> **Avoid Drag and Drop:** Dragging text from a browser window into the overlay fires standard HTML5 `dragleave` and `dragend` events inside the browser. Proctoring tools track these events and will register that text was dragged outside. Always use copy-paste or hotkey-based copy-injection.

> [!IMPORTANT]
> **Silent Repositioning:** When in strict proctored environments, do not drag the overlay with your mouse. Instead, press `Alt + Z` and use the **Arrow Keys** to move the window. This is completely internal and undetectable.

> [!NOTE]
> **Docks to Edges:** When you hide the overlay, it shrinks into a thin, glassy strip on the closest screen boundary. It dynamically curves its inner corners (matching Windows 11/macOS design systems) and supports custom translucency. Simply hover over it or press `Alt + Z` + `Space` to restore it.

---

## 🛠️ Compilation & Setup

### API Keys
Ensure a `.env` file exists in the directory containing your API keys:
```env
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
OPENROUTER_API_KEY=your_openrouter_key
```

### Building the Executable
Run `build_exe.bat`. This:
1. Activates the `.venv` virtual environment.
2. Builds the executable `SystemAudioEngine.exe` into the `dist/` folder using the optimized spec file `SystemAudioEngine.spec`.
3. **Preserves previous builds** (does not delete existing executables in `dist`).
