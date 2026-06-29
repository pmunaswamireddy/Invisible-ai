import os
import sys
import time
import subprocess
import urllib.request
import urllib.parse
import json
import uuid
import re
from PyQt5.QtCore import QThread, pyqtSignal
from utils import get_app_dir

# --- TTSWorker ---
class TTSWorker(QThread):
    speech_status_signal = pyqtSignal(str) # "speaking" or "idle"
    
    def __init__(self):
        super().__init__()
        self.queue = []
        self.running = True
        self.lock = threading_lock = None # resolved below
        import threading
        self.lock = threading.Lock()
        self.voice_name = "Microsoft Zira" # default
        
    def set_voice(self, voice_name):
        with self.lock:
            self.voice_name = voice_name
            
    def _speak_via_powershell(self, text, voice_name=None):
        import html as html_lib
        
        # Clean text
        clean = text.replace('"', "'").replace('`', "'").replace('\n', ' ')
        clean = html_lib.escape(clean)
        
        # SAPI Speech compilation
        ps = f"""
        $speaker = New-Object -ComObject SAPI.SpVoice
        $voice = $speaker.GetVoices() | Where-Object {{ $_.GetDescription() -like '*{voice_name}*' }}
        if ($voice) {{
            $speaker.Voice = $voice
        }}
        $speaker.Speak("{clean}")
        """
        
        try:
            subprocess.run(
                ['powershell', '-WindowStyle', 'Hidden', '-NonInteractive', '-Command', ps],
                capture_output=True, text=True, timeout=15, creationflags=0x08000000
            )
        except Exception:
            pass

    def run(self):
        while self.running:
            text_to_speak = None
            voice_to_use = None
            with self.lock:
                if self.queue:
                    text_to_speak = self.queue.pop(0)
                    voice_to_use = self.voice_name
            
            if text_to_speak:
                self.speech_status_signal.emit("speaking")
                self._speak_via_powershell(text_to_speak, voice_to_use)
                self.speech_status_signal.emit("idle")
            else:
                self.msleep(100)
                
    def speak(self, text):
        # Strip markdown syntax before reading aloud
        import re
        clean = re.sub(r'```.*?```', '', text, flags=re.DOTALL) # remove code blocks
        clean = re.sub(r'[*#_`~>\[\]()-]', '', clean) # remove formatting characters
        clean = clean.strip()
        
        if not clean:
            return
            
        with self.lock:
            self.queue.append(clean)
            
    def stop_speech(self):
        with self.lock:
            self.queue.clear()
        # Kill running powershell instances
        try:
            subprocess.run(
                ['taskkill', '/f', '/im', 'powershell.exe'],
                capture_output=True, timeout=2, creationflags=0x08000000
            )
        except Exception:
            pass
        self.speech_status_signal.emit("idle")
        
    def stop(self):
        self.running = False
        self.stop_speech()
        self.wait()

# --- DictationWorker ---
class DictationWorker(QThread):
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def run(self):
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            with sr.Microphone() as source:
                self.status_signal.emit("Listening...")
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, timeout=5, phrase_time_limit=15)
                
            self.status_signal.emit("Recognizing...")
            text = r.recognize_google(audio)
            self.finished_signal.emit(text)
        except ImportError:
            self.error_signal.emit("Please run: pip install SpeechRecognition pyaudio")
        except Exception as e:
            self.error_signal.emit(f"Mic error: {str(e)}")

# --- VoiceSetupWorker ---
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

# --- SystemAudioWorker ---
class SystemAudioWorker(QThread):
    finished_signal = pyqtSignal(str) # Transcribed text
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    
    def __init__(self, duration=10):
        super().__init__()
        self.duration = duration
        self.running = True
        
    def stop(self):
        self.running = False
        
    def run(self):
        import pyaudio
        import wave
        import tempfile
        
        p = pyaudio.PyAudio()
        
        # Search for Windows WASAPI loopback device
        wasapi_info = None
        for i in range(p.get_host_api_count()):
            api_info = p.get_host_api_info_by_index(i)
            if "wasapi" in api_info.get('name', '').lower():
                wasapi_info = api_info
                break
                
        if not wasapi_info:
            self.error_signal.emit("Windows WASAPI audio driver not found.")
            p.terminate()
            return
            
        loopback_dev = None
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev.get('hostApi') == wasapi_info.get('index') and dev.get('maxInputChannels') > 0:
                if "loopback" in dev.get('name', '').lower():
                    loopback_dev = dev
                    break
                    
        if not loopback_dev:
            default_idx = wasapi_info.get('defaultInputDevice')
            if default_idx is not None and default_idx >= 0:
                loopback_dev = p.get_device_info_by_index(default_idx)
                
        if not loopback_dev:
            self.error_signal.emit("System loopback audio device not found.")
            p.terminate()
            return
            
        dev_idx = loopback_dev.get('index')
        rate = int(loopback_dev.get('defaultSampleRate', 48000))
        channels = 2
        
        self.status_signal.emit("🎤 Recording System Audio...")
        
        frames = []
        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=dev_idx,
                frames_per_buffer=1024
            )
        except Exception as e:
            self.error_signal.emit(f"Failed to open loopback stream: {e}")
            p.terminate()
            return
            
        ticks = int(rate / 1024 * self.duration)
        for _ in range(ticks):
            if not self.running:
                break
            try:
                data = stream.read(1024, exception_on_overflow=False)
                frames.append(data)
            except Exception:
                pass
                
        stream.stop_stream()
        stream.close()
        p.terminate()
        
        if not frames:
            self.error_signal.emit("No audio frames recorded.")
            return
            
        temp_wav = os.path.join(tempfile.gettempdir(), f"loopback_temp_{uuid.uuid4().hex[:8]}.wav")
        try:
            wf = wave.open(temp_wav, 'wb')
            wf.setnchannels(channels)
            wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
            wf.setframerate(rate)
            wf.writeframes(b''.join(frames))
            wf.close()
        except Exception as e:
            self.error_signal.emit(f"WAV save error: {e}")
            return
            
        self.status_signal.emit("🧠 Transcribing System Audio...")
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            with sr.AudioFile(temp_wav) as source:
                audio = r.record(source)
            text = r.recognize_google(audio)
            self.finished_signal.emit(text)
        except Exception as e:
            self.error_signal.emit(f"Transcription error: {str(e)}")
        finally:
            try:
                os.remove(temp_wav)
            except Exception:
                pass

# --- AITaskWorker ---
class AITaskWorker(QThread):
    finished_signal = pyqtSignal(str, str, str) # type, content, raw_code
    error_signal = pyqtSignal(str)

    def __init__(self, provider, api_keys, task_type, prompt, history=None, image_path=None, system_prompt=None):
        super().__init__()
        self.provider = provider
        self.api_keys = api_keys
        self.task_type = task_type
        self.prompt = prompt
        self.history = history or []
        self.image_path = image_path
        self.system_prompt = system_prompt

    def run(self):
        import urllib.request
        import urllib.parse
        try:
            if self.task_type == "imagine":
                import time
                encoded_prompt = urllib.parse.quote(self.prompt)
                url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true"
                filename = f"generated_image_{int(time.time())}.jpg"
                save_path = os.path.join(get_app_dir(), filename)
                
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
                with urllib.request.urlopen(req) as response, open(save_path, 'wb') as out_file:
                    out_file.write(response.read())
                self.finished_signal.emit("image", save_path, "")
                
            elif self.task_type in ["text", "vision"]:
                system_prompt = self.system_prompt or (
                    "You are a highly capable AI assistant operating within a stealth overlay. Provide direct, concise answers. "
                    "If providing code, always wrap it in ``` backticks. You have access to the user's Chat History. "
                    "Use context intelligently: if the user's request is a continuation, reference past history. "
                    "If they change the subject or upload a completely new image, treat it as a new context while retaining general memory."
                )
                
                history_text = ""
                for msg in self.history:
                    if msg['role'] == 'user': history_text += f"\nUser: {msg['content']}"
                    elif msg['role'] == 'ai': history_text += f"\nAI: {msg['content']}"
                    
                full_prompt = f"{system_prompt}\n\nChat History:{history_text}\n\nCurrent User Request: {self.prompt}"
                text_response = ""
                active_provider = "Gemini" if self.task_type == "vision" else self.provider
                
                if active_provider == "Gemini":
                    try:
                        import google.generativeai as genai
                        import PIL.Image
                    except ImportError:
                        self.error_signal.emit("google-generativeai and pillow are not installed.")
                        return
                    
                    key = self.api_keys.get("gemini", "")
                    if not key:
                        self.error_signal.emit("Gemini API Key is missing.")
                        return
                    genai.configure(api_key=key)
                    
                    try:
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        if self.task_type == "vision" and self.image_path:
                            contents = [full_prompt]
                            paths = self.image_path if isinstance(self.image_path, list) else [self.image_path]
                            for p_path in paths:
                                if os.path.exists(p_path):
                                    contents.append(PIL.Image.open(p_path))
                            response = model.generate_content(contents)
                        else:
                            response = model.generate_content(full_prompt)
                        text_response = response.text
                    except Exception as e:
                        try:
                            model = genai.GenerativeModel('gemini-1.5-flash')
                            if self.task_type == "vision" and self.image_path:
                                contents = [full_prompt]
                                paths = self.image_path if isinstance(self.image_path, list) else [self.image_path]
                                for p_path in paths:
                                    if os.path.exists(p_path):
                                        contents.append(PIL.Image.open(p_path))
                                response = model.generate_content(contents)
                            else:
                                response = model.generate_content(full_prompt)
                            text_response = response.text
                        except Exception as e2:
                            self.error_signal.emit(f"Gemini API Error: {str(e2)}")
                            return
                            
                elif active_provider == "Groq":
                    try:
                        import groq
                    except ImportError:
                        self.error_signal.emit("groq is not installed.")
                        return
                    
                    key = self.api_keys.get("groq", "")
                    if not key:
                        self.error_signal.emit("Groq API Key is missing.")
                        return
                    client = groq.Groq(api_key=key)
                    
                    chat_completion = client.chat.completions.create(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": self.prompt}
                        ],
                        model="llama-3.3-70b-versatile",
                    )
                    text_response = chat_completion.choices[0].message.content
                    
                elif active_provider == "Custom API":
                    try:
                        import openai
                    except ImportError:
                        self.error_signal.emit("openai is not installed.")
                        return
                        
                    base_url = self.api_keys.get("custom_api_base", "")
                    api_key = self.api_keys.get("custom_api_key", "")
                    model_name = self.api_keys.get("custom_api_model", "")
                    
                    if not api_key:
                        self.error_signal.emit("Custom API Key is missing. Configure it in Manager Panel.")
                        return
                    if not base_url:
                        base_url = "https://api.openai.com/v1"
                    if not model_name:
                        model_name = "gpt-4o"
                        
                    client = openai.OpenAI(base_url=base_url, api_key=api_key)
                    messages = [{"role": "system", "content": system_prompt}]
                    for msg in self.history:
                        if msg['role'] == 'user': messages.append({"role": "user", "content": msg['content']})
                        elif msg['role'] == 'ai': messages.append({"role": "assistant", "content": msg['content']})
                    messages.append({"role": "user", "content": self.prompt})
                    
                    chat_completion = client.chat.completions.create(
                        messages=messages,
                        model=model_name,
                    )
                    text_response = chat_completion.choices[0].message.content
                    
                elif active_provider == "OpenRouter":
                    try:
                        import openai
                    except ImportError:
                        self.error_signal.emit("openai is not installed.")
                        return
                        
                    key = self.api_keys.get("openrouter", "")
                    if not key:
                        self.error_signal.emit("OpenRouter API Key is missing.")
                        return
                    client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)
                    
                    try:
                        req = urllib.request.Request(
                            "https://openrouter.ai/api/v1/models",
                            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                        )
                        with urllib.request.urlopen(req, timeout=5) as response:
                            models_data = json.loads(response.read().decode('utf-8'))
                            models_list = [m['id'] for m in models_data.get('data', [])]
                    except Exception:
                        models_list = []
                        
                    target_model = "meta-llama/llama-3.3-70b-instruct:free"
                    if target_model not in models_list:
                        free_models = [m for m in models_list if ":free" in m]
                        if free_models:
                            target_model = free_models[0]
                        elif models_list:
                            target_model = models_list[0]
                            
                    messages = [{"role": "system", "content": system_prompt}]
                    for msg in self.history:
                        if msg['role'] == 'user': messages.append({"role": "user", "content": msg['content']})
                        elif msg['role'] == 'ai': messages.append({"role": "assistant", "content": msg['content']})
                    messages.append({"role": "user", "content": self.prompt})
                    
                    chat_completion = client.chat.completions.create(
                        messages=messages,
                        model=target_model,
                    )
                    text_response = chat_completion.choices[0].message.content
                    
                elif active_provider == "Google Web Search":
                    gemini_key = self.api_keys.get("gemini", "")
                    if not gemini_key:
                        self.error_signal.emit("Google Web Search requires a Gemini API Key.")
                        return
                    
                    search_query = self.prompt
                    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(search_query)}"
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    
                    try:
                        with urllib.request.urlopen(req) as response:
                            html_content = response.read().decode('utf-8')
                    except Exception as e:
                        self.error_signal.emit(f"Search retrieval failed: {e}")
                        return
                        
                    import html as html_lib
                    from xml.etree import ElementTree
                    
                    results = []
                    links = re.findall(r'<a class="result__url" href="([^"]+)"', html_content)
                    snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html_content, re.DOTALL)
                    titles = re.findall(r'<a class="result__snippet"[^>]*>.*?</a>.*?<a class="result__snippet"[^>]*>.*?</a>', html_content, re.DOTALL)
                    
                    titles_clean = re.findall(r'<a class="result__link"[^>]*>(.*?)</a>', html_content, re.DOTALL)
                    
                    count = 0
                    text_response = "🌐 **Google Search Context:**\n\n"
                    for idx in range(min(len(links), len(snippets), len(titles_clean))):
                        if count >= 3:
                            break
                        url = links[idx]
                        if "duckduckgo.com" in url:
                            continue
                        parsed_url = urllib.parse.urlparse(url)
                        q_params = urllib.parse.parse_qs(parsed_url.query)
                        if 'uddg' in q_params:
                            url = q_params['uddg'][0]
                            
                        desc = snippets[idx]
                        desc = re.sub(r'<[^>]+>', '', desc)
                        desc = html_lib.unescape(desc).strip()
                        
                        title = titles_clean[idx]
                        title = re.sub(r'<[^>]+>', '', title)
                        title = html_lib.unescape(title).strip()
                        
                        if url and desc:
                            try:
                                url = urllib.parse.unquote(url)
                            except: pass
                            
                            text_response += f"**[{title}]({url})**\n{desc}\n\n"
                            count += 1
                            
                        if count > 0:
                            gemini_key = self.api_keys.get("gemini", "")
                            if gemini_key:
                                try:
                                    import google.generativeai as genai
                                    genai.configure(api_key=gemini_key)
                                    
                                    target_model = "gemini-2.5-flash"
                                    try:
                                        models_list = genai.list_models()
                                        for m in models_list:
                                            if "gemini-2.5-flash" in m.name:
                                                target_model = m.name
                                                break
                                    except:
                                        pass
                                        
                                    model = genai.GenerativeModel(target_model)
                                    search_prompt = f"Using the following DuckDuckGo Search context:\n{text_response}\n\nAnswer this request: {self.prompt}"
                                    response = model.generate_content(search_prompt)
                                    text_response += "\n\n💡 **AI Summary:**\n" + response.text
                                except Exception as e:
                                    text_response += f"\n\n*(Failed to summarize search results: {e})*"
                    
                code_match = re.search(r'```(?:python|javascript|js|html|css|c|cpp|java|go|rust)?\n(.*?)```', text_response, re.DOTALL)
                raw_code = code_match.group(1).strip() if code_match else ""
                
                self.finished_signal.emit(self.task_type, text_response, raw_code)
        except Exception as e:
            self.error_signal.emit(str(e))
