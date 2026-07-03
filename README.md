# 🔒 Invisible AI Overlay (Stealth Assistant Engine)

A highly optimized, completely invisible, floating AI assistant designed for Windows 10 and Windows 11. It sits transparently on top of your workspace and offers latency-free assistance, hardware-level typing simulation, screen scanning, and custom API tracking. 

---

## 🌟 Complete Feature Catalog

### 1. 🔒 Strict Stealth Mode (Zero Capture & Focus Detection)
* **Anti-Screen Capture (`WDA_EXCLUDEFROMCAPTURE`):** Leveraging the native Win32 `SetWindowDisplayAffinity` API, the window is rendered 100% black/invisible to OBS, Discord, screenshots, and automated exam proctoring tools.
* **Bypassed Focus Triggers (`WS_EX_NOACTIVATE`):** Running with strict Win32 extended window styles means clicking on the overlay never steals active focus from your foreground browser window.
* **Stealth Click Routing (`WH_MOUSE_LL`):** A low-level hardware mouse hook intercepts clicks when hovering over active settings widgets, handles them internally, and blocks them from notifying the OS. The active web page remains focused without triggering `mouseleave` or blur events.
* **Theme-less Transparent Dock Bar:** When minimized to the edge, the overlay collapses into a thin, glassy border indicator that bypasses theme styles, keeping it entirely non-descript and transparent.

### 2. ⚡ Latency & UI Optimization
* **On-Demand Hit Testing:** The resource-heavy 50Hz polling timers have been replaced with event-driven hooks. The CPU stays at 0% usage at rest.
* **Asynchronous Page Loading:** The settings interface opens instantly. Complex background tasks like API usage statistics and quota tracking are run asynchronously using deferred timers (`QTimer.singleShot`), keeping UI rendering completely smooth.
* **Zero Decompression Lag:** UPX compression is disabled during PyInstaller compilation. This prevents the ~2-second boot delay caused by runtime unpacking and helps avoid security heuristics flagging the file as a packed binary.

### 3. 🛡️ Hardware Ghost Typing (Anti-Clipboard Detection)
* **Real Hardware Simulation:** Types responses character-by-character into the active window using Windows kernel `SendInput` events with `KEYEVENTF_UNICODE`. 
* **Site Bypass:** Since it emulates direct physical keystrokes, it cannot be blocked or logged by browsers or websites that disable copy-paste or monitor the clipboard.

### 4. 📊 Active Quota & Reset Tracker
* **Remaining Usability Count:** Tracks how many requests you have used since midnight against standard daily caps:
  * **Gemini (Free tier):** 1,500 daily requests.
  * **Groq:** 14,400 daily requests.
  * **OpenRouter (Free endpoints):** 200 daily requests.
  * **NVIDIA (Nemotron credits):** 1,000 daily requests.
* **Reset Countdown:** Shows the exact time remaining in hours and minutes until the midnight UTC quota reset boundary.

### 5. 📡 Dynamic Working Model Fetcher
* **Live Refresh:** Queries the active provider APIs dynamically to pull the list of currently working online models.
* **Filter Heuristics:** Automatically filters out Whisper/voice-transcription models or guardrails from your dropdown lists, so only valid text/code-generation models are presented.

---

## 🎹 Keyboard Shortcuts & Command Mode

Press the leader chord **`Alt + Z`** to enter **Command Mode**. Once active, you can trigger settings, rotate models, or shift focus using these keys:

| Hotkey | Action |
| :--- | :--- |
| **`Esc`** | Deactivate Command Mode |
| **`Space`** or **`H`** | Toggle visibility (minimize/dock to edge or restore) |
| **`K`** | Toggle Ghost Typing / Typist Mode |
| **`P`** | Rotate AI Model / Provider (Gemini ⇄ Groq ⇄ OpenRouter ⇄ NVIDIA) |
| **`S`** | Scan Screen (captures background bounds to Gemini Vision) |
| **`I`** | Inject latest AI code block via hardware keystrokes |
| **`1-9`** | Inject specific indexed code block (Top row or Numpad) |
| **`D`** | Send Chat Message |
| **`C`** | Clear current chat history |
| **`T`** | Toggle Light / Dark Theme |
| **`U`** | Single Voice Input (Listen once and type to chat box) |
| **`M`** | Toggle Continuous Dictation Mode |
| **`V`** | Toggle Speaker TTS Mute / Unmute |
| **`O`** | Rotate TTS Voice Model |
| **`X`** | Force Exit Application |
| **`▲ / ▼ / ◀ / ▶`** | **Reposition Overlay:** Move window by 20px (retains Command Mode for repeated adjustments) |

---

## ⚙️ Settings Guide

Open the settings frame using the **Settings** button in the sidebar. The model options page contains:

* **API Keys Configuration:** Inputs for Gemini, Groq, OpenRouter, and NVIDIA keys. 
  * Fields are styled with high-visibility purple borders that highlight on focus.
  * **👁️ Toggle View:** Shows or hides password text.
  * **📋 Paste:** Copies contents of clipboard into the key field.
  * **🔑 Reset Keys:** Instantly overwrites active settings fields back to the default keys loaded from `.env`.
* **Model Dropdowns:** Populated with standard models by default. Dropdowns feature hover-state highlight styling that prevents blackout errors.
* **📡 Fetch Models:** Scans your active API keys and updates the dropdown menus with live online working models.
* **💾 Save Config:** Saves current models, keys, and positioning metrics, then restores stealth transparent background flags.

---

## 🛡️ Anti-Detection & Anonymous Interaction Guidelines

To ensure complete stealth and zero trace in highly restrictive environments, adhere strictly to these rules:

1. **Never Drag and Drop Text:** Dragging text from a web browser into the overlay fires standard HTML5 events (`dragleave`, `dragend`) in the browser. Proctoring tools track these and flag that text left the window. Always type your queries or use OCR screen scanning (`Alt + Z` → `S`).
2. **Never Use the Mouse to Reposition:** Dragging the overlay window moves your cursor away from your work and leaves a trajectory path. Use the internal chord commands (`Alt + Z` followed by the **Arrow Keys**) to reposition the window silently.
3. **Use Background Focus Mode:** Keep the input mode set to **Background Mode**. This ensures the overlay remains click-through and never takes window focus.
4. **Clean Reset:** When using public or shared computers, use **🔑 Reset Keys** inside Settings to instantly override customized fields with environmental variables, leaving no personal API key traces in the local `settings.json`.

---

## 🚀 Windows SmartScreen Evasion & Compilation

When compiling Python code to a standalone `.exe` using PyInstaller, Windows SmartScreen will often block the program because it lacks a digital signature and reputation history. The project contains a native solution for this.

### Why this build is recognized as clean:
1. **UPX Compression is Disabled:** Suspicious packing engines are avoided, lowering heuristic scanning flags.
2. **PE Metadata is Embedded:** `file_version_info.txt` injects complete, authentic metadata (Company Name, Version, Copyright) into the PE headers.
3. **Local Authenticode Signing:** You can self-sign the binary to establish local trust.

### How to Build and Self-Sign:
1. Run **`build_exe.bat`**. This will activate the virtual environment and compile the binary.
2. At the end of compilation, the builder will ask:
   ```cmd
   Do you want to self-sign the executable to bypass Windows SmartScreen? (y/n):
   ```
3. Type **`y`**. It will request Administrator access to generate a local code signing certificate, register it in your computer's Trusted Root Certification Authorities and Trusted Publishers stores, and sign `dist/SystemAudioEngine.exe` with it.
4. The signed executable will launch without any SmartScreen warnings on that machine.
