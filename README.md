# Invisible AI Overlay

A highly stealthy, ultra-lightweight, floating AI assistant that sits completely invisibly on your Windows desktop. 

## Features
- **Total Invisibility:** Built to bypass Windows Taskbar, hidden from system trays, and invisible to screen recording software (OBS/Discord) via native Windows API hooks (`WDA_EXCLUDEFROMCAPTURE`).
- **Universal Portability:** Compiles to a single `.exe` file that can be carried on a USB drive and run instantly on any Windows 10/11 system without requiring Python or Admin permissions.
- **Smart Model Fallback:** Automatically scrapes OpenRouter's live API to detect and switch to working free AI models if standard ones go down.
- **Persistent Memory:** Safely diverts all chat history, dynamic imagery, and configuration settings natively into `%APPDATA%\InvisibleAI` so your data persists forever across application updates.

## Build Instructions
Run `build_exe.bat` to automatically clean the workspace, install dependencies into a virtual environment, and compile `overlay.py` into `SystemAudioEngine.exe`.

## API Setup
To use on a fresh machine, ensure a `.env` file containing `GEMINI_API_KEY`, `GROQ_API_KEY`, and `OPENROUTER_API_KEY` is present in your build environment. If you build via `build_exe.bat`, these keys are safely hardcoded into the compiled byte-code for standalone portability!
