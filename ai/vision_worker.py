import os
import io
import json
import time
import base64
import logging
from PyQt5.QtCore import QThread, pyqtSignal, QBuffer, QByteArray, QIODevice
from PyQt5.QtWidgets import QApplication

logger = logging.getLogger("invisibleai")

class VisionInterviewWorker(QThread):
    result_signal = pyqtSignal(str, str) # question, answer
    chunk_signal = pyqtSignal(str)
    
    def __init__(self, image_data, voice_text="", api_keys=None, active_provider=None, provider_models=None):
        super().__init__()
        self.image_data = image_data
        self.voice_text = voice_text
        self.api_keys = api_keys or {}
        self.active_provider = active_provider or "NVIDIA"
        self.provider_models = provider_models or {}
        
    def run(self):
        try:
            import requests
            from PIL import Image
            
            img_data_bytes = base64.b64decode(self.image_data)
            img = Image.open(io.BytesIO(img_data_bytes))
            img.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
            
            output_buffer = io.BytesIO()
            img.convert('RGB').save(output_buffer, format="JPEG", quality=50, optimize=True)
            compressed_b64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
            
            app = QApplication.instance()
            groq_key = ""
            if hasattr(app, '_overlay_instance') and app._overlay_instance:
                groq_key = app._overlay_instance.api_keys.get("groq", "")
            
            prompt = (
                "You are an elite stealth AI meeting & technical interview co-pilot. Your primary job is to help the candidate excel by combining live screen perception and transcribed conversation audio in real-time.\n\n"
                "=== STEP 1: SCREEN & ACTIVITY CLASSIFICATION ===\n"
                "Identify what the user is currently doing on screen:\n"
                "• CODING: LeetCode, HackerRank, IDE (VS Code/PyCharm), Terminal, or active code file.\n"
                "• REASONING / APTITUDE: Math formulas, quantitative questions, logic puzzles, diagrams, MCQs, or test papers.\n"
                "• MEETING / BEHAVIORAL Q&A: Zoom, Teams, Google Meet, slide deck, or general discussion.\n\n"
                "=== STEP 2: INTELLIGENT SPEAKER RESOLUTION (Interviewer vs Candidate) ===\n"
                "Distinguish who spoke in the transcribed audio:\n"
                "• INTERVIEWER STATEMENT: Explicit questions, prompts, test cases, or constraints spoken by the interviewer (e.g. 'Can you optimize this function?', 'What is the time complexity?', 'Tell me about a time you handled a conflict').\n"
                "• CANDIDATE SELF-TALK: The candidate thinking out loud, reading code, or describing what they are typing (e.g. 'I am iterating through the array', 'Let me check this condition'). DO NOT mistake candidate self-talk as an interviewer question.\n\n"
                "=== STEP 3: MULTIMODAL CONTEXT SYNTHESIS & DOMAIN RESOLUTION ===\n"
                "• For CODING: If there is an algorithm statement, task comment (e.g. `# TODO: reverse linked list`), unfulfilled function signature, or verbal coding constraint, output clean production-grade code. Auto-detect programming language. Provide optimal time and space complexity.\n"
                "• For APTITUDE & LOGICAL REASONING: Calculate the solution immediately. Output the **FINAL ANSWER** upfront in bold, followed by a step-by-step logic breakdown.\n"
                "• For BEHAVIORAL & EXPERIENTIAL Q&A: Synthesize a confident, natural 3-4 bullet point answer using the STAR method (Situation, Task, Action, Result) ready for the candidate to speak out loud.\n\n"
                "=== OUTPUT FORMAT ===\n"
                "Output strictly in this format:\n\n"
                "QUESTION:\n[Brief summary of detected problem/question with domain category tag e.g. (Coding | Aptitude | Behavioral Q&A)]\n\n"
                "SOLUTION:\n[Your precise answer formatted neatly according to the domain category.]\n\n"
                "CRITICAL: If there is no active interviewer question in the audio AND the screen contains only empty/idle UI or fully finished code without task comments or undefined functions, reply EXACTLY with the single word: NO_QUESTION."
            )
            if self.voice_text:
                prompt += f"\n\nTranscribed Audio Stream: '{self.voice_text}'"
            
            full_text = ""
            import overlay
            global_gemini_throttled_until = getattr(overlay, 'GLOBAL_GEMINI_THROTTLED_UNTIL', 0.0)
            
            providers_to_try = [self.active_provider]
            for p in ["Gemini", "NVIDIA"]:
                if p not in providers_to_try:
                    providers_to_try.append(p)
                    
            success = False
            for provider in providers_to_try:
                try:
                    if provider == "Gemini":
                        if time.time() < global_gemini_throttled_until:
                            continue
                        gemini_key = self.api_keys.get("gemini", "").strip()
                        if not gemini_key:
                            raise Exception("Gemini API key is empty")
                        import google.genai as genai
                        g_client = genai.Client(api_key=gemini_key)
                        chosen_model = self.provider_models.get("gemini", "gemini-flash-latest")
                        if chosen_model not in ["gemini-flash-latest", "gemini-2.5-flash"]:
                            chosen_model = "gemini-flash-latest"
                        
                        response = g_client.models.generate_content_stream(
                            model=chosen_model,
                            contents=[prompt, img]
                        )
                        full_text = ""
                        for chunk in response:
                            try:
                                if chunk.text:
                                    full_text += chunk.text
                                    self.chunk_signal.emit(chunk.text)
                            except Exception:
                                pass
                        if full_text.strip():
                            success = True
                            break
                            
                    elif provider == "NVIDIA":
                        nv_key = self.api_keys.get("nvidia", "").strip()
                        if not nv_key:
                            nv_key = os.environ.get("NVIDIA_API_KEY", "")
                        invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
                        headers = {
                            "Authorization": f"Bearer {nv_key}",
                            "Accept": "text/event-stream"
                        }
                        chosen_nv_model = self.provider_models.get("nvidia", "meta/llama-3.2-11b-vision-instruct")
                        payload = {
                            "model": chosen_nv_model,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt},
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/jpeg;base64,{compressed_b64}"
                                            }
                                        }
                                    ]
                                }
                            ],
                            "max_tokens": 1024,
                            "temperature": 0.20,
                            "stream": True
                        }
                        res = requests.post(invoke_url, headers=headers, json=payload, timeout=12.0, stream=True)
                        if res.status_code == 200:
                            full_text = ""
                            for line in res.iter_lines():
                                if line:
                                    decoded = line.decode('utf-8').strip()
                                    if decoded.startswith("data:"):
                                        data_str = decoded[5:].strip()
                                        if data_str == "[DONE]": break
                                        try:
                                            d_json = json.loads(data_str)
                                            c_text = d_json.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                            if c_text:
                                                full_text += c_text
                                                self.chunk_signal.emit(c_text)
                                        except Exception: pass
                            if full_text.strip():
                                success = True
                                break
                        else:
                            raise Exception(f"NVIDIA API Error: HTTP {res.status_code}")
                except Exception as p_err:
                    if "429" in str(p_err) or "RESOURCE_EXHAUSTED" in str(p_err):
                        overlay.GLOBAL_GEMINI_THROTTLED_UNTIL = time.time() + 3600.0
                    continue

            if not success and groq_key and self.voice_text:
                try:
                    import groq
                    g_client = groq.Groq(api_key=groq_key, timeout=8.0)
                    g_res = g_client.chat.completions.create(
                        messages=[{"role": "user", "content": f"{prompt}\n\n[Audio Only Context: {self.voice_text}]"}],
                        model=self.provider_models.get("groq", "llama-3.3-70b-versatile"),
                        stream=True
                    )
                    full_text = "⚠️ *[Vision AI Throttled: Answer synthesized from Audio Stream]*\n\n"
                    self.chunk_signal.emit(full_text)
                    for chunk in g_res:
                        ct = chunk.choices[0].delta.content or ""
                        if ct:
                            full_text += ct
                            self.chunk_signal.emit(ct)
                    success = True
                except Exception:
                    pass

            if not success or not full_text.strip():
                self.result_signal.emit("NO_QUESTION", "")
                return

            if "NO_QUESTION" in full_text.strip() and len(full_text.strip()) < 30:
                self.result_signal.emit("NO_QUESTION", "")
                return

            question_part = ""
            answer_part = full_text
            if "QUESTION:" in full_text and "SOLUTION:" in full_text:
                try:
                    parts = full_text.split("SOLUTION:")
                    question_part = parts[0].replace("QUESTION:", "").strip()
                    answer_part = parts[1].strip()
                except Exception:
                    pass
            elif "QUESTION:" in full_text:
                question_part = full_text.replace("QUESTION:", "").strip()

            self.result_signal.emit(question_part, answer_part)
        except Exception as e:
            self.result_signal.emit("Error", str(e))

class OCRWorker(QThread):
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, gemini_key="", nvidia_key="", pixmap_or_list=None, chosen_model="gemini-flash-latest", api_key=None):
        super().__init__()
        if api_key and not gemini_key:
            self.gemini_key = api_key
        else:
            self.gemini_key = gemini_key or ""
        self.nvidia_key = nvidia_key or os.environ.get("NVIDIA_API_KEY", "")
        self.pixmap_or_list = pixmap_or_list
        self.chosen_model = chosen_model if chosen_model in ["gemini-flash-latest", "gemini-2.5-flash"] else "gemini-flash-latest"

    def run(self):
        try:
            import PIL.Image
            
            if isinstance(self.pixmap_or_list, list):
                pixmaps = self.pixmap_or_list
            else:
                pixmaps = [self.pixmap_or_list]
                
            imgs = []
            b64_imgs = []
            for pixmap in pixmaps:
                byte_array = QByteArray()
                buffer = QBuffer(byte_array)
                buffer.open(QIODevice.WriteOnly)
                pixmap.save(buffer, "PNG")
                img_bytes = byte_array.data()
                img = PIL.Image.open(io.BytesIO(img_bytes))
                
                if img.width > 1600 or img.height > 1600:
                    img.thumbnail((1600, 1600), PIL.Image.Resampling.LANCZOS)
                imgs.append(img)
                
                buf_jpeg = io.BytesIO()
                img.convert('RGB').save(buf_jpeg, format="JPEG", quality=75)
                b64_str = base64.b64encode(buf_jpeg.getvalue()).decode('utf-8')
                b64_imgs.append(b64_str)
                
            import overlay
            global_gemini_throttled_until = getattr(overlay, 'GLOBAL_GEMINI_THROTTLED_UNTIL', 0.0)

            if self.gemini_key and time.time() >= global_gemini_throttled_until:
                try:
                    import google.genai as genai
                    g_client = genai.Client(api_key=self.gemini_key)
                    if len(imgs) > 1:
                        prompt = (
                            "Perform OCR on these sequential images of a scrolling screen capture. "
                            "Extract all text, code, and content exactly as it appears. "
                            "Combine the content from all images in correct order (from first to last), "
                            "automatically aligning overlapping lines and deduplicating any content that "
                            "appears in multiple consecutive images. "
                            "Do not add any introduction, headers, markdown explanations, or footnotes. "
                            "Just return the raw unified text/code."
                        )
                    else:
                        prompt = (
                            "Perform OCR on this image. Extract all text, code, and content exactly as it appears. "
                            "Do not add any introduction, headers, markdown explanations, or footnotes. "
                            "Just return the raw extracted text/code."
                        )
                        
                    response = g_client.models.generate_content(
                        model=self.chosen_model,
                        contents=[prompt] + imgs
                    )
                    extracted_text = response.text
                    if extracted_text and extracted_text.strip():
                        self.finished_signal.emit(extracted_text)
                        return
                except Exception as g_err:
                    if "429" in str(g_err) or "RESOURCE_EXHAUSTED" in str(g_err):
                        overlay.GLOBAL_GEMINI_THROTTLED_UNTIL = time.time() + 3600.0
                    logger.warning("Gemini OCR failed/throttled, falling back to NVIDIA Vision: %s", g_err)

            try:
                import openai
                nv_key = self.nvidia_key or os.environ.get("NVIDIA_API_KEY", "")
                client = openai.OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=nv_key, timeout=8.0)
                
                content_list = [
                    {"type": "text", "text": "Perform OCR on these screenshot images. Extract all visible text, code, and content exactly as it appears with correct spacing and formatting. Do not add any introductory or meta text, return only the extracted text/code."}
                ]
                for b64_str in b64_imgs:
                    content_list.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_str}"}})

                res = client.chat.completions.create(
                    model="meta/llama-3.2-11b-vision-instruct",
                    messages=[{"role": "user", "content": content_list}],
                    max_tokens=1500,
                    temperature=0.1
                )
                extracted_text = res.choices[0].message.content or ""
                if extracted_text and extracted_text.strip():
                    self.finished_signal.emit(extracted_text)
                    return
                else:
                    raise Exception("NVIDIA Vision OCR returned empty response")
            except Exception as nv_err:
                raise Exception(f"OCR failed across all engines: {nv_err}")

        except Exception as e:
            self.error_signal.emit(str(e))
