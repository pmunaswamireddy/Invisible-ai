import re
import queue
import logging
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication

logger = logging.getLogger("invisibleai")

class TTSWorker(QThread):
    speech_status_signal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.q = queue.Queue()
        self.selected_voice_name = None  # None = system default
        self.current_proc = None
        
    def set_voice(self, voice_name):
        """Set voice by display name (used by SelectVoice in SAPI)."""
        self.selected_voice_name = voice_name
        
    def _speak_via_powershell(self, text, voice_name=None):
        """Speak text using Windows SAPI via PowerShell subprocess (fresh process every call)."""
        import subprocess
        # Sanitize text for PowerShell single-quoted string
        safe = text.replace("'", "").replace('"', '').replace('`', '').replace('\n', ' ')
        # Sanitize voice name
        voice_cmd = ''
        if voice_name:
            safe_v = voice_name.replace("'", '').replace('"', '')
            voice_cmd = f'$s.SelectVoice("{safe_v}"); '
        ps = (
            'Add-Type -AssemblyName System.Speech; '
            '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
            f'{voice_cmd}'
            '$s.Rate = 0; '
            f'$s.Speak("{safe}"); '
            '$s.Dispose()'
        )
        try:
            self.current_proc = subprocess.Popen(
                ['powershell', '-WindowStyle', 'Hidden', '-NonInteractive', '-Command', ps],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            self.current_proc.wait(timeout=90)
        except Exception as e:
            logger.warning('TTS PowerShell error: %s', e)
        finally:
            self.current_proc = None
        
    def run(self):
        while True:
            text = self.q.get()
            if text is None:
                break
            # Clean markdown/code from spoken text
            text_to_speak = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
            text_to_speak = re.sub(r'[`*#]', '', text_to_speak).strip()
            if text_to_speak:
                self.speech_status_signal.emit(True)
                self._speak_via_powershell(text_to_speak, self.selected_voice_name)
                self.speech_status_signal.emit(False)

    def speak(self, text):
        self.q.put(text)
        
    def stop_speech(self):
        # Drain queue
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        # Kill any running subprocess
        if self.current_proc and self.current_proc.poll() is None:
            try:
                self.current_proc.kill()
            except Exception:
                pass
        
    def stop(self):
        self.stop_speech()
        self.q.put(None)

class DictationWorker(QThread):
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def run(self):
        try:
            overlay = getattr(QApplication.instance(), '_overlay_instance', None)
            if not overlay or not getattr(overlay, '_shared_recognizer', None):
                self.error_signal.emit("Speech recognition engine not initialized.")
                return
                
            r = overlay._shared_recognizer
            mic = overlay._shared_microphone
            
            self.status_signal.emit("Listening Mic...")
            with mic as source:
                r.adjust_for_ambient_noise(source, duration=0.1)
                audio = r.listen(source, timeout=4.5, phrase_time_limit=15)
                
            if audio:
                self.status_signal.emit("Recognizing Mic...")
                text = r.recognize_google(audio).strip()
                if text:
                    self.finished_signal.emit(text)
                else:
                    self.error_signal.emit("No speech recognized.")
            else:
                self.error_signal.emit("No audio captured.")
        except Exception as e:
            self.error_signal.emit(f"Audio capture error: {str(e)}")

class VoiceSetupWorker(QThread):
    setup_done = pyqtSignal(object, object) # recognizer, microphone
    error_signal = pyqtSignal(str)

    def run(self):
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            m = sr.Microphone()
            with m as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
            self.setup_done.emit(r, m)
        except ImportError:
            self.error_signal.emit("Please run: pip install SpeechRecognition pyaudio")
        except Exception as e:
            self.error_signal.emit(str(e))
