import os
import json
import time
import re
import urllib.request
import urllib.parse
import logging
from PyQt5.QtCore import QThread, pyqtSignal
from core.constants import get_app_dir

logger = logging.getLogger("invisibleai")

class AITaskWorker(QThread):
    finished_signal = pyqtSignal(str, str, str) # type, content, raw_code
    error_signal = pyqtSignal(str)
    chunk_signal = pyqtSignal(str)

    def __init__(self, provider, api_keys, task_type, prompt, history=None, image_path=None, provider_models=None):
        super().__init__()
        self.provider = provider
        self.api_keys = api_keys
        self.task_type = task_type
        self.prompt = prompt
        self.history = history or []
        self.image_path = image_path
        self.provider_models = provider_models or {}

    def run(self):
        try:
            if self.task_type == "imagine":
                encoded_prompt = urllib.parse.quote(self.prompt)
                url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true"
                filename = f"generated_image_{int(time.time())}.jpg"
                save_path = os.path.join(get_app_dir(), filename)
                
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
                with urllib.request.urlopen(req) as response, open(save_path, 'wb') as out_file:
                    out_file.write(response.read())
                self.finished_signal.emit("image", save_path, "")
                
            elif self.task_type in ["text", "vision"]:
                system_prompt = (
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
                
                import overlay
                global_gemini_throttled_until = getattr(overlay, 'GLOBAL_GEMINI_THROTTLED_UNTIL', 0.0)
                
                if self.task_type == "vision":
                    if self.provider == "NVIDIA" or time.time() < global_gemini_throttled_until or not self.api_keys.get("gemini", "").strip():
                        active_provider = "NVIDIA"
                    else:
                        active_provider = "Gemini"
                else:
                    active_provider = self.provider
                
                if active_provider == "Gemini":
                    try:
                        import google.genai as genai
                        from google.genai import types as genai_types
                        import PIL.Image
                    except ImportError:
                        self.error_signal.emit("google-genai and pillow are not installed.")
                        return
                    
                    key = self.api_keys.get("gemini", "")
                    if not key:
                        self.error_signal.emit("Gemini API Key is missing.")
                        return
                    g_client = genai.Client(api_key=key)
                    
                    try:
                        chosen_model = self.provider_models.get("gemini", "gemini-flash-latest")
                        if self.task_type == "vision" and self.image_path and os.path.exists(self.image_path):
                            img = PIL.Image.open(self.image_path)
                            response = g_client.models.generate_content_stream(
                                model=chosen_model,
                                contents=[full_prompt, img]
                            )
                        else:
                            response = g_client.models.generate_content_stream(
                                model=chosen_model,
                                contents=full_prompt
                            )
                        
                        text_response = ""
                        for chunk in response:
                            try:
                                if chunk.text:
                                    text_response += chunk.text
                                    self.chunk_signal.emit(chunk.text)
                            except Exception:
                                pass
                    except Exception as ge:
                        try:
                            if self.task_type == "vision" and self.image_path and os.path.exists(self.image_path):
                                img = PIL.Image.open(self.image_path)
                                response = g_client.models.generate_content_stream(
                                    model='gemini-flash-latest',
                                    contents=[full_prompt, img]
                                )
                            else:
                                response = g_client.models.generate_content_stream(
                                    model='gemini-flash-latest',
                                    contents=full_prompt
                                )
                            
                            text_response = ""
                            for chunk in response:
                                try:
                                    if chunk.text:
                                        text_response += chunk.text
                                        self.chunk_signal.emit(chunk.text)
                                except Exception:
                                    pass
                        except Exception as ge2:
                            if self.task_type == "vision" and self.image_path and os.path.exists(self.image_path):
                                nv_key = self.api_keys.get("nvidia", "").strip() or os.environ.get("NVIDIA_API_KEY", "")
                                try:
                                    import base64
                                    import openai
                                    with open(self.image_path, "rb") as img_f:
                                        b64_img = base64.b64encode(img_f.read()).decode('utf-8')
                                    nv_client = openai.OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=nv_key, timeout=25.0)
                                    nv_response = nv_client.chat.completions.create(
                                        model="meta/llama-3.2-11b-vision-instruct",
                                        messages=[
                                            {
                                                "role": "user",
                                                "content": [
                                                    {"type": "text", "text": full_prompt},
                                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                                                ]
                                            }
                                        ],
                                        stream=True
                                    )
                                    text_response = "⚠️ *[Gemini Throttled: Seamlessly fell back to NVIDIA Vision]*\n\n"
                                    self.chunk_signal.emit(text_response)
                                    for chunk in nv_response:
                                        chunk_text = chunk.choices[0].delta.content or ""
                                        if chunk_text:
                                            text_response += chunk_text
                                            self.chunk_signal.emit(chunk_text)
                                    self.finished_signal.emit("text", text_response, "")
                                    return
                                except Exception as nv_err:
                                    logger.warning("NVIDIA Vision fallback failed: %s", nv_err)

                            groq_key = self.api_keys.get("groq", "")
                            if groq_key:
                                try:
                                    import groq
                                    client = groq.Groq(api_key=groq_key, timeout=15.0)
                                    messages = [{"role": "system", "content": system_prompt}]
                                    for msg in self.history:
                                        if msg['role'] == 'user': messages.append({"role": "user", "content": msg['content']})
                                        elif msg['role'] == 'ai': messages.append({"role": "assistant", "content": msg['content']})
                                    messages.append({"role": "user", "content": self.prompt})
                                    response = client.chat.completions.create(
                                        messages=messages,
                                        model=self.provider_models.get("groq", "llama-3.3-70b-versatile"),
                                        stream=True
                                    )
                                    text_response = "⚠️ *[Gemini Throttled: Seamlessly fell back to Groq]*\n\n"
                                    self.chunk_signal.emit(text_response)
                                    for chunk in response:
                                        chunk_text = chunk.choices[0].delta.content or ""
                                        if chunk_text:
                                            text_response += chunk_text
                                            self.chunk_signal.emit(chunk_text)
                                    self.finished_signal.emit("text", text_response, "")
                                    return
                                except Exception:
                                    pass
                            raise Exception(f"Gemini error/quota limit reached: {ge2}")
                    
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
                    client = groq.Groq(api_key=key, timeout=15.0)
                    messages = [{"role": "system", "content": system_prompt}]
                    for msg in self.history:
                        if msg['role'] == 'user': messages.append({"role": "user", "content": msg['content']})
                        elif msg['role'] == 'ai': messages.append({"role": "assistant", "content": msg['content']})
                    messages.append({"role": "user", "content": self.prompt})
                    
                    try:
                        response = client.chat.completions.create(
                            messages=messages,
                            model=self.provider_models.get("groq", "llama-3.3-70b-versatile"),
                            stream=True
                        )
                        text_response = ""
                        for chunk in response:
                            chunk_text = chunk.choices[0].delta.content or ""
                            if chunk_text:
                                text_response += chunk_text
                                self.chunk_signal.emit(chunk_text)
                    except Exception as e:
                        gemini_key = self.api_keys.get("gemini", "")
                        if gemini_key:
                            try:
                                import google.genai as genai
                                g_client = genai.Client(api_key=gemini_key)
                                response = g_client.models.generate_content_stream(
                                    model='gemini-flash-latest',
                                    contents=full_prompt
                                )
                                text_response = "⚠️ *[Groq Error: Fell back to Gemini]*\n\n"
                                self.chunk_signal.emit(text_response)
                                for chunk in response:
                                    try:
                                        if chunk.text:
                                            text_response += chunk.text
                                            self.chunk_signal.emit(chunk.text)
                                    except Exception:
                                        pass
                            except Exception as ge_fallback:
                                self.error_signal.emit(f"Groq Error: {e} and Gemini fallback failed: {ge_fallback}")
                                return
                        else:
                            self.error_signal.emit(f"Groq Error: {e} (No Gemini key for fallback)")
                            return
                    
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
                    client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key, timeout=15.0)
                    
                    try:
                        req = urllib.request.Request(
                            "https://openrouter.ai/api/v1/models",
                            headers={"User-Agent": "Mozilla/5.0"}
                        )
                        with urllib.request.urlopen(req, timeout=5.0) as response:
                            models_data = json.loads(response.read())
                        
                        free_models = []
                        for m in models_data.get('data', []):
                            pricing = m.get('pricing', {})
                            prompt_price = pricing.get('prompt', 0)
                            try:
                                is_free = float(prompt_price) == 0.0
                            except (ValueError, TypeError):
                                is_free = False
                            
                            if is_free and m.get('id', '').endswith(':free'):
                                free_models.append(m['id'])
                    except Exception as e:
                        logger.warning("Failed to fetch OpenRouter free models dynamically: %s", e)
                        free_models = []
                        
                    if not free_models:
                        free_models = [
                            "google/gemini-2.0-flash:free",
                            "meta-llama/llama-3.3-70b-instruct:free",
                            "qwen/qwen-2.5-7b-instruct:free",
                            "meta-llama/llama-3.2-3b-instruct:free",
                            "mistralai/mistral-7b-instruct:free"
                        ]
                        
                    chosen_or_model = self.provider_models.get("openrouter", "google/gemini-2.0-flash:free")
                    if chosen_or_model:
                        free_models = [chosen_or_model] + [m for m in free_models if m != chosen_or_model]
                        
                    messages = [{"role": "system", "content": system_prompt}]
                    for msg in self.history:
                        if msg['role'] == 'user': messages.append({"role": "user", "content": msg['content']})
                        elif msg['role'] == 'ai': messages.append({"role": "assistant", "content": msg['content']})
                    messages.append({"role": "user", "content": self.prompt})
                    
                    completion = None
                    last_err = None
                    for model_id in free_models[:10]:
                        try:
                            response = client.chat.completions.create(
                                extra_headers={"HTTP-Referer": "https://invisible.ai", "X-Title": "Stealth AI"},
                                model=model_id,
                                messages=messages,
                                stream=True
                            )
                            text_response = ""
                            for chunk in response:
                                chunk_text = chunk.choices[0].delta.content or ""
                                if chunk_text:
                                    text_response += chunk_text
                                    self.chunk_signal.emit(chunk_text)
                            completion = True
                            break
                        except Exception as e:
                            last_err = e
                            continue
                    
                    if not completion:
                        gemini_key = self.api_keys.get("gemini", "")
                        if gemini_key:
                            try:
                                import google.genai as genai
                                g_client = genai.Client(api_key=gemini_key)
                                response = g_client.models.generate_content_stream(
                                    model='gemini-flash-latest',
                                    contents=full_prompt
                                )
                                text_response = "⚠️ *[OpenRouter Error: Fell back to Gemini]*\n\n"
                                self.chunk_signal.emit(text_response)
                                for chunk in response:
                                    try:
                                        if chunk.text:
                                            text_response += chunk.text
                                            self.chunk_signal.emit(chunk.text)
                                    except Exception:
                                        pass
                            except Exception as ge_fallback:
                                self.error_signal.emit(f"All OpenRouter free models failed. Last Error: {last_err} and Gemini fallback failed: {ge_fallback}")
                                return
                        else:
                            self.error_signal.emit(f"All OpenRouter free models failed. Last Error: {last_err}")
                            return
 
                elif active_provider == "NVIDIA":
                    try:
                        import openai
                    except ImportError:
                        self.error_signal.emit("openai is not installed.")
                        return
                        
                    key = self.api_keys.get("nvidia", "")
                    if not key:
                        self.error_signal.emit("NVIDIA API Key is missing.")
                        return
                        
                    client = openai.OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=key, timeout=15.0)
                    
                    if self.task_type == "vision" and self.image_path and os.path.exists(self.image_path):
                        import base64
                        try:
                            with open(self.image_path, "rb") as img_file:
                                base64_image = base64.b64encode(img_file.read()).decode('utf-8')
                            
                            messages = [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": full_prompt},
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/png;base64,{base64_image}"
                                            }
                                        }
                                    ]
                                }
                            ]
                            
                            chosen_nv_model = self.provider_models.get("nvidia", "meta/llama-3.2-11b-vision-instruct")
                            vision_model = chosen_nv_model if "vision" in chosen_nv_model.lower() else "meta/llama-3.2-11b-vision-instruct"
                            response = client.chat.completions.create(
                                model=vision_model,
                                messages=messages,
                                max_tokens=1024,
                                temperature=0.70,
                                top_p=1.00,
                                stream=True
                            )
                            text_response = ""
                            for chunk in response:
                                chunk_text = chunk.choices[0].delta.content or ""
                                if chunk_text:
                                    text_response += chunk_text
                                    self.chunk_signal.emit(chunk_text)
                        except Exception as e:
                            fallback_nv = "meta/llama-3.2-11b-vision-instruct"
                            try:
                                response = client.chat.completions.create(
                                    model=fallback_nv,
                                    messages=messages,
                                    max_tokens=1024,
                                    temperature=0.70,
                                    top_p=1.00,
                                    stream=True
                                )
                                text_response = f"⚠️ *[NVIDIA Error: {e} - Fell back to {fallback_nv}]*\n\n"
                                self.chunk_signal.emit(text_response)
                                for chunk in response:
                                    chunk_text = chunk.choices[0].delta.content or ""
                                    if chunk_text:
                                        text_response += chunk_text
                                        self.chunk_signal.emit(chunk_text)
                            except Exception as e2:
                                gemini_key = self.api_keys.get("gemini", "")
                                if gemini_key:
                                    try:
                                        import google.genai as genai
                                        g_client = genai.Client(api_key=gemini_key)
                                        response = g_client.models.generate_content_stream(
                                            model='gemini-flash-latest',
                                            contents=full_prompt
                                        )
                                        text_response = "⚠️ *[NVIDIA Error: Fell back to Gemini]*\n\n"
                                        self.chunk_signal.emit(text_response)
                                        for chunk in response:
                                            try:
                                                if chunk.text:
                                                    text_response += chunk.text
                                                    self.chunk_signal.emit(chunk.text)
                                            except Exception:
                                                pass
                                    except Exception as ge_fallback:
                                        self.error_signal.emit(f"NVIDIA Error: {e} (Fallback {fallback_nv} failed: {e2}) and Gemini fallback failed: {ge_fallback}")
                                        return
                                else:
                                    self.error_signal.emit(f"NVIDIA Error: {e} (Fallback {fallback_nv} failed: {e2}, no Gemini key)")
                                    return

                    else:
                        messages = [{"role": "system", "content": system_prompt}]
                        for msg in self.history:
                            if msg['role'] == 'user': messages.append({"role": "user", "content": msg['content']})
                            elif msg['role'] == 'ai': messages.append({"role": "assistant", "content": msg['content']})
                        messages.append({"role": "user", "content": self.prompt})
                        
                        chosen_nv_model = self.provider_models.get("nvidia", "meta/llama-3.3-70b-instruct")
                        try:
                            response = client.chat.completions.create(
                                model=chosen_nv_model,
                                messages=messages,
                                max_tokens=1024,
                                temperature=0.70,
                                top_p=1.00,
                                stream=True
                            )
                            text_response = ""
                            for chunk in response:
                                chunk_text = chunk.choices[0].delta.content or ""
                                if chunk_text:
                                    text_response += chunk_text
                                    self.chunk_signal.emit(chunk_text)
                        except Exception as e:
                            fallback_nv = "meta/llama-3.3-70b-instruct"
                            try:
                                response = client.chat.completions.create(
                                    model=fallback_nv,
                                    messages=messages,
                                    max_tokens=1024,
                                    temperature=0.70,
                                    top_p=1.00,
                                    stream=True
                                )
                                text_response = f"⚠️ *[NVIDIA Error: {e} - Fell back to {fallback_nv}]*\n\n"
                                self.chunk_signal.emit(text_response)
                                for chunk in response:
                                    chunk_text = chunk.choices[0].delta.content or ""
                                    if chunk_text:
                                        text_response += chunk_text
                                        self.chunk_signal.emit(chunk_text)
                            except Exception as e2:
                                gemini_key = self.api_keys.get("gemini", "")
                                if gemini_key:
                                    try:
                                        import google.genai as genai
                                        g_client = genai.Client(api_key=gemini_key)
                                        response = g_client.models.generate_content_stream(
                                            model='gemini-flash-latest',
                                            contents=full_prompt
                                        )
                                        text_response = "⚠️ *[NVIDIA Error: Fell back to Gemini]*\n\n"
                                        self.chunk_signal.emit(text_response)
                                        for chunk in response:
                                            try:
                                                if chunk.text:
                                                    text_response += chunk.text
                                                    self.chunk_signal.emit(chunk.text)
                                            except Exception:
                                                pass
                                    except Exception as ge_fallback:
                                        self.error_signal.emit(f"NVIDIA Error: {e} (Fallback {fallback_nv} failed: {e2}) and Gemini fallback failed: {ge_fallback}")
                                        return
                                else:
                                    self.error_signal.emit(f"NVIDIA Error: {e} (Fallback {fallback_nv} failed: {e2}, no Gemini key)")
                                    return

                elif active_provider == "Web2API":
                    try:
                        import openai
                    except ImportError:
                        self.error_signal.emit("openai is not installed.")
                        return
                        
                    web2_entry = self.api_keys.get("web2api", "").strip() or "http://localhost:8081/v1"
                    base_url = "http://localhost:8081/v1"
                    key = "sk-web2api"
                    
                    if "http://" in web2_entry or "https://" in web2_entry:
                        base_url = web2_entry.rstrip('/')
                        if not base_url.endswith('/v1'):
                            base_url += '/v1'
                    else:
                        if web2_entry:
                            key = web2_entry

                    client = openai.OpenAI(base_url=base_url, api_key=key, timeout=45.0, max_retries=2)
                    messages = [{"role": "system", "content": system_prompt}]
                    for msg in self.history:
                        if msg['role'] == 'user': messages.append({"role": "user", "content": msg['content']})
                        elif msg['role'] == 'ai': messages.append({"role": "assistant", "content": msg['content']})
                    messages.append({"role": "user", "content": self.prompt})
                    
                    chosen_web2_model = self.provider_models.get("web2api", "gemini-3.5-flash-thinking")
                    
                    try:
                        response = client.chat.completions.create(
                            model=chosen_web2_model,
                            messages=messages,
                            stream=True
                        )
                        text_response = ""
                        for chunk in response:
                            delta = chunk.choices[0].delta if chunk.choices else None
                            chunk_text = ""
                            if delta:
                                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                                    chunk_text = delta.reasoning_content
                                elif delta.content:
                                    chunk_text = delta.content
                            if chunk_text:
                                text_response += chunk_text
                                self.chunk_signal.emit(chunk_text)
                        
                        if not text_response.strip():
                            raise Exception("Web2API returned an empty response. Triggering failover.")
                    except Exception as e:
                        groq_key = self.api_keys.get("groq", "")
                        if groq_key:
                            try:
                                import groq
                                g_client = groq.Groq(api_key=groq_key, timeout=15.0)
                                g_response = g_client.chat.completions.create(
                                    messages=messages,
                                    model=self.provider_models.get("groq", "llama-3.3-70b-versatile"),
                                    stream=True
                                )
                                text_response = "⚠️ *[Web2API Connection Error: Fell back to Groq]*\n\n"
                                self.chunk_signal.emit(text_response)
                                for chunk in g_response:
                                    chunk_text = chunk.choices[0].delta.content or ""
                                    if chunk_text:
                                        text_response += chunk_text
                                        self.chunk_signal.emit(chunk_text)
                                self.finished_signal.emit("text", text_response, "")
                                return
                            except Exception as groq_err:
                                logger.warning("Groq fallback failed: %s", groq_err)

                        gemini_key = self.api_keys.get("gemini", "")
                        if gemini_key:
                            try:
                                import google.genai as genai
                                g_client = genai.Client(api_key=gemini_key)
                                response = g_client.models.generate_content_stream(
                                    model='gemini-flash-latest',
                                    contents=full_prompt
                                )
                                text_response = f"⚠️ *[Web2API Error: {e} - Fell back to Gemini]*\n\n"
                                self.chunk_signal.emit(text_response)
                                for chunk in response:
                                    try:
                                        if chunk.text:
                                            text_response += chunk.text
                                            self.chunk_signal.emit(chunk.text)
                                    except Exception:
                                        pass
                                self.finished_signal.emit("text", text_response, "")
                                return
                            except Exception as ge_fallback:
                                logger.warning("Gemini fallback failed: %s", ge_fallback)
                        
                        self.error_signal.emit(f"Web2API Error: {e} (Ensure gemini-web2api server is running at {base_url})")
                        return

                elif active_provider == "Google Web Search":
                    self.finished_signal.emit("system", "Scraping web results...", "")
                    
                    query = urllib.parse.quote(self.prompt)
                    url = f"https://html.duckduckgo.com/html/?q={query}"
                    req = urllib.request.Request(
                        url, 
                        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                    )
                    
                    try:
                        with urllib.request.urlopen(req) as response:
                            html = response.read().decode('utf-8')
                            
                        results = re.findall(r'<a class="result__url" href="([^"]+)".*?>\s*(.*?)\s*</a>.*?<a class="result__snippet".*?>\s*(.*?)\s*</a>', html, re.DOTALL)
                        
                        text_response = "### 🌐 Live Web Search Results:\n\n"
                        count = 0
                        for link, title, desc in results[:5]:
                            title = re.sub(r'<.*?>', '', title).strip()
                            desc = re.sub(r'<.*?>', '', desc).strip()
                            url = link.strip()
                            if "uddg=" in url:
                                try:
                                    encoded_url = url.split("uddg=")[1]
                                    if "&amp;rut=" in encoded_url:
                                        encoded_url = encoded_url.split("&amp;rut=")[0]
                                    elif "&rut=" in encoded_url:
                                        encoded_url = encoded_url.split("&rut=")[0]
                                    url = urllib.parse.unquote(encoded_url)
                                except Exception:
                                    pass
                            
                            text_response += f"**[{title}]({url})**\n{desc}\n\n"
                            count += 1
                            
                        if count > 0:
                            gemini_key = self.api_keys.get("gemini", "")
                            if gemini_key:
                                try:
                                    import google.genai as genai
                                    from google.genai import types as genai_types
                                    g_client = genai.Client(api_key=gemini_key)
                                    
                                    target_model = "gemini-flash-latest"
                                    ai_prompt = (
                                        f"User Request: {self.prompt}\n\nLive Web Search Results:\n{text_response}\n\n"
                                        f"Please provide a comprehensive answer to the user's request. "
                                        f"Use the provided web search results as context and cite them where appropriate. "
                                        f"IMPORTANT: You are a senior developer. If the user asks how to do something (especially programming/technical), "
                                        f"you MUST provide a full, easy, step-by-step guide with COMPLETE code examples for every step. "
                                        f"Even if the search results do not contain the exact code, use your own expert programming knowledge to generate the code examples and solve the request."
                                    )
                                    self.finished_signal.emit("system", f"Synthesizing AI summary using {target_model}...", "")
                                    safety_settings = [
                                        genai_types.SafetySetting(category=genai_types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=genai_types.HarmBlockThreshold.BLOCK_NONE),
                                        genai_types.SafetySetting(category=genai_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=genai_types.HarmBlockThreshold.BLOCK_NONE),
                                        genai_types.SafetySetting(category=genai_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=genai_types.HarmBlockThreshold.BLOCK_NONE),
                                        genai_types.SafetySetting(category=genai_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=genai_types.HarmBlockThreshold.BLOCK_NONE),
                                    ]
                                    config = genai_types.GenerateContentConfig(safety_settings=safety_settings)
                                    
                                    response = g_client.models.generate_content_stream(
                                        model=target_model,
                                        contents=ai_prompt,
                                        config=config
                                    )
                                    
                                    res_text = ""
                                    for chunk in response:
                                        try:
                                            if chunk.text:
                                                res_text += chunk.text
                                                self.chunk_signal.emit(chunk.text)
                                        except Exception:
                                            pass
                                            
                                    if not res_text:
                                        res_text = "⚠️ *[Gemini response was blocked by safety filters or returned empty]*"
                                        self.chunk_signal.emit(res_text)
                                    
                                    clean_sources = text_response.replace("### 🌐 Live Web Search Results:\n\n", "")
                                    self.chunk_signal.emit("\n\n---\n**Sources Scanned:**\n" + clean_sources)
                                    text_response = f"{res_text}\n\n---\n**Sources Scanned:**\n" + clean_sources
                                except Exception as ai_e:
                                    groq_key = self.api_keys.get("groq", "")
                                    if groq_key:
                                        try:
                                            import groq
                                            client = groq.Groq(api_key=groq_key, timeout=15.0)
                                            ai_prompt = f"User Request: {self.prompt}\n\nLive Web Search Results:\n{text_response}\n\nPlease provide a comprehensive answer using these search results."
                                            self.finished_signal.emit("system", "Synthesizing AI summary using Groq fallback...", "")
                                            resp = client.chat.completions.create(
                                                messages=[{"role": "user", "content": ai_prompt}],
                                                model=self.provider_models.get("groq", "llama-3.3-70b-versatile"),
                                                stream=True
                                            )
                                            res_text = ""
                                            for c in resp:
                                                ct = c.choices[0].delta.content or ""
                                                if ct:
                                                    res_text += ct
                                                    self.chunk_signal.emit(ct)
                                            clean_sources = text_response.replace("### 🌐 Live Web Search Results:\n\n", "")
                                            self.chunk_signal.emit("\n\n---\n**Sources Scanned:**\n" + clean_sources)
                                            text_response = f"{res_text}\n\n---\n**Sources Scanned:**\n" + clean_sources
                                        except Exception:
                                            text_response += f"\n\n*(AI Synthesis failed: {ai_e})*"
                                    else:
                                        text_response += f"\n\n*(AI Synthesis failed: {ai_e})*"
                            else:
                                text_response += "\n\n*(Note: Add a Gemini API Key in the top settings to automatically synthesize these web results!)*"
                        else:
                            text_response += "No results found or search engine blocked the request."
                    except Exception as e:
                        text_response = f"### 🌐 Web Search Failed:\n\n{str(e)}"
                        
                # Extract code block if present
                code_blocks = re.findall(r'```(?:\w+)?\n(.*?)```', text_response, re.DOTALL)
                raw_code = code_blocks[-1].strip() if code_blocks else ""
                
                self.finished_signal.emit("text", text_response, raw_code)
                
        except Exception as e:
            self.error_signal.emit(str(e))
