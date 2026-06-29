# Invisible AI Control Hub

A highly stealthy, ultra-lightweight, floating AI assistant that sits completely invisibly on your Windows desktop. Built for maximum privacy, latency-free operation, and advanced hardware-level interaction. Equipped with a visible settings controller/paywall manager and a stealth overlay engine.

---

## 🌟 Key Features

### 1. 🔒 Strict Stealth Mode (Zero Detection)
- **Anti-Screen Capture:** Invisible to screen capture software, recorders, and screenshots (OBS, Discord, Proctoring tools) using the native Windows API `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`.
- **Bypassed Focus Triggers:** Runs with `WS_EX_NOACTIVATE` so clicking the interface never steals focus from the foreground browser window (the browser stays active).
- **Stealth Clicks (WM_MOUSELEAVE Bypass):** Unlike standard overlays that toggle focus on hover (triggering mouse-leave events on the active window), this overlay remains `WS_EX_TRANSPARENT` constantly. Clicks on the overlay are intercepted at the hardware level using `WH_MOUSE_LL` hooks, blocked from the OS, and routed directly to the overlay's widgets. **The browser never knows you clicked outside.**
- **Hotkey Repositioning:** Silently move the overlay using keyboard shortcut chords. This avoids moving the mouse to the overlay, which could leave a trail or trigger mouse-out alerts.

### 2. 🎛️ Control Hub Settings Manager (`Manager.exe`)
- **Centralized Panel:** A visible settings panel to configure Gemini, Groq, OpenRouter, and custom OpenAI-compatible endpoints.
- **System Prompts Manager:** Add, edit, delete, and select active system prompts to control the AI's response style.
- **Paywall Integration:** Built-in UPI payment QR generation, 12-digit UTR verification pings to Firestore, and Discord webhook notifications.

### 3. 🔊 System Audio Loopback Transcription (Meetings & Interviews)
- **WASAPI Capture:** Capture and transcribe system audio output (e.g. other speakers in Zoom, Google Meet, Teams, or browser audio) using Windows WASAPI loopback, transcribing questions in real-time.

### 4. 📎 File Drag-and-Drop Context
- Drag and drop code, configuration, or document files directly onto the overlay window to append their contents to your prompt as context chips.

---

## 🎹 Keyboard Shortcuts & Chord Mode

Press the leader chord **`Alt + Z`** to activate **Command Mode**, followed by one of the keys below:

| Hotkey | Action |
| :--- | :--- |
| **`Esc`** | Deactivate Command Mode |
| **`Space`** or **`H`** | Toggle visibility (dock to edge) |
| **`K`** | Toggle Ghost Typing / Typist Mode |
| **`P`** | Rotate AI Model / Provider (Gemini ⇄ Groq ⇄ OpenRouter ⇄ Custom API ⇄ Search) |
| **`A`** | Toggle System Audio loopback recording (Meetings capture) |
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
> **Drag and Drop from Web Pages:** Dragging text from a browser window into the overlay fires standard HTML5 `dragleave` and `dragend` events inside the browser. Proctoring tools track these events. Only drag and drop **local files** (from Explorer) into the overlay, as they are processed entirely internally and are safe. For browser text, use copy-paste or hotkey-based scanning.

> [!IMPORTANT]
> **Silent Repositioning:** When in strict proctored environments, do not drag the overlay with your mouse. Instead, press `Alt + Z` and use the **Arrow Keys** to move the window. This is completely internal and undetectable.

> [!NOTE]
> **Docks to Edges:** When you hide the overlay, it shrinks into a thin, glassy strip on the closest screen boundary. It dynamically curves its inner corners (matching Windows 11/macOS design systems) and supports custom translucency. Simply hover over it or press `Alt + Z` + `Space` to restore it.

---

## 🛠️ Compilation & Setup

### API Keys
All configurations are stored in `%APPDATA%\InvisibleAI\settings.json` (created automatically by the settings Manager panel).

### Building the Executable
Run `build_exe.bat`. This:
1. Activates the `.venv` virtual environment.
2. Compiles both `Manager.exe` and `SystemAudioEngine.exe` into the `dist/` folder using the dual-target configuration spec `SystemAudioEngine.spec`.
3. Preserves previous builds.
