import os
import json
import time
import threading
import http.server
import socketserver
import logging

logger = logging.getLogger("invisibleai")

# Shared global overlay reference accessor
def get_overlay_instance():
    import overlay
    return getattr(overlay, '_overlay_instance', None)

class Web2APIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path.rstrip('/') in ["/v1/models", "/models"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            models_data = {
                "object": "list",
                "data": [
                    {"id": "gemini-3.5-flash-thinking", "object": "model", "owned_by": "web2api"},
                    {"id": "gemini-3.6-flash", "object": "model", "owned_by": "web2api"},
                    {"id": "gemini-3.5-flash-thinking-lite", "object": "model", "owned_by": "web2api"},
                    {"id": "gemini-3.1-pro", "object": "model", "owned_by": "web2api"},
                    {"id": "gemini-auto", "object": "model", "owned_by": "web2api"}
                ]
            }
            self.wfile.write(json.dumps(models_data).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path.rstrip('/') in ["/v1/chat/completions", "/chat/completions"]:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode('utf-8'))
                messages = data.get("messages", [])
                model_name = data.get("model", "gemini-3.5-flash-thinking")
                stream = data.get("stream", True)
                
                gemini_key = os.environ.get("GEMINI_API_KEY", "")
                _overlay_instance = get_overlay_instance()
                if _overlay_instance and hasattr(_overlay_instance, 'api_keys'):
                    gemini_key = _overlay_instance.api_keys.get("gemini", "") or gemini_key
                
                auth_header = self.headers.get("Authorization", "")
                if auth_header.startswith("Bearer ") and auth_header != "Bearer sk-web2api":
                    gemini_key = auth_header[7:].strip()
                    
                prompt_parts = []
                for m in messages:
                    role = m.get("role", "user")
                    content = m.get("content", "")
                    if role == "system":
                        prompt_parts.append(f"System: {content}\n")
                    elif role == "assistant":
                        prompt_parts.append(f"AI: {content}\n")
                    else:
                        prompt_parts.append(f"User: {content}\n")
                
                if _overlay_instance and hasattr(_overlay_instance, 'log_event'):
                    _overlay_instance.log_event(f"Web2API background request received for model '{model_name}'", "ongoing")
                    
                full_prompt = "\n".join(prompt_parts)
                
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream" if stream else "application/json")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                full_text = ""
                success = False

                # 1. Try Gemini if key is valid
                if gemini_key:
                    try:
                        import google.genai as genai
                        from google.genai import types as genai_types
                        g_client = genai.Client(api_key=gemini_key)
                        target_model = "gemini-flash-latest"
                        if stream:
                            response = g_client.models.generate_content_stream(
                                model=target_model,
                                contents=full_prompt
                            )
                            for chunk in response:
                                try:
                                    c_text = chunk.text
                                except Exception:
                                    c_text = ""
                                if c_text:
                                    full_text += c_text
                                    chunk_data = {
                                        "id": "chatcmpl-web2api",
                                        "object": "chat.completion.chunk",
                                        "created": int(time.time()),
                                        "model": model_name,
                                        "choices": [{"index": 0, "delta": {"content": c_text}, "finish_reason": None}]
                                    }
                                    self.wfile.write(f"data: {json.dumps(chunk_data)}\n\n".encode("utf-8"))
                                    self.wfile.flush()
                        else:
                            response = g_client.models.generate_content(
                                model=target_model,
                                contents=full_prompt
                            )
                            try:
                                full_text = response.text or ""
                            except Exception:
                                full_text = ""
                        if full_text.strip():
                            success = True
                    except Exception as ge:
                        logger.warning("Web2API Gemini generation error: %s", ge)

                # 2. Fall back to Groq if Gemini failed
                if not success:
                    try:
                        groq_key = ""
                        if _overlay_instance and hasattr(_overlay_instance, 'api_keys'):
                            groq_key = _overlay_instance.api_keys.get("groq", "")
                        if not groq_key:
                            groq_key = os.environ.get("GROQ_API_KEY", "")
                        
                        if groq_key:
                            import groq
                            client = groq.Groq(api_key=groq_key)
                            g_messages = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
                            if stream:
                                response = client.chat.completions.create(
                                    model="llama-3.3-70b-versatile",
                                    messages=g_messages,
                                    stream=True
                                )
                                for chunk in response:
                                    c_text = chunk.choices[0].delta.content or ""
                                    if c_text:
                                        full_text += c_text
                                        chunk_data = {
                                            "id": "chatcmpl-web2api",
                                            "object": "chat.completion.chunk",
                                            "created": int(time.time()),
                                            "model": model_name,
                                            "choices": [{"index": 0, "delta": {"content": c_text}, "finish_reason": None}]
                                        }
                                        self.wfile.write(f"data: {json.dumps(chunk_data)}\n\n".encode("utf-8"))
                                        self.wfile.flush()
                            else:
                                response = client.chat.completions.create(
                                    model="llama-3.3-70b-versatile",
                                    messages=g_messages,
                                    stream=False
                                )
                                full_text = response.choices[0].message.content or ""
                            if full_text.strip():
                                success = True
                    except Exception as ge:
                        logger.warning("Web2API Groq fallback error: %s", ge)

                # 3. Fall back to NVIDIA if Groq failed
                if not success:
                    try:
                        nv_key = ""
                        if _overlay_instance and hasattr(_overlay_instance, 'api_keys'):
                            nv_key = _overlay_instance.api_keys.get("nvidia", "")
                        if not nv_key:
                            nv_key = os.environ.get("NVIDIA_API_KEY", "")
                        
                        if nv_key:
                            import requests
                            invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
                            headers = {"Authorization": f"Bearer {nv_key}", "Accept": "text/event-stream" if stream else "application/json"}
                            nv_model = "meta/llama-3.2-11b-vision-instruct"
                            if _overlay_instance and hasattr(_overlay_instance, 'provider_models'):
                                nv_model = _overlay_instance.provider_models.get("nvidia", nv_model)
                            
                            payload = {"model": nv_model, "messages": messages, "max_tokens": 2048, "temperature": 0.2, "stream": stream}
                            nv_res = requests.post(invoke_url, headers=headers, json=payload, timeout=8.0, stream=stream)
                            if nv_res.status_code == 200:
                                if stream:
                                    for line in nv_res.iter_lines():
                                        if line:
                                            line_str = line.decode('utf-8')
                                            if line_str.startswith("data: "):
                                                self.wfile.write(f"{line_str}\n\n".encode('utf-8'))
                                                self.wfile.flush()
                                else:
                                    res_json = nv_res.json()
                                    full_text = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                                success = True
                    except Exception as nve:
                        logger.warning("Web2API NVIDIA fallback error: %s", nve)

                if _overlay_instance and hasattr(_overlay_instance, 'log_event'):
                    if success:
                        _overlay_instance.log_event(f"Web2API request completed ({len(full_text)} chars).", "success")
                    else:
                        _overlay_instance.log_event("Web2API request failed across all providers.", "error")

                # Send final stream finish marker or non-stream JSON
                if stream:
                    try:
                        self.wfile.write(b"data: [DONE]\n\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                        pass
                else:
                    resp_data = {
                        "id": "chatcmpl-web2api",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": model_name,
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": full_text}, "finish_reason": "stop"}]
                    }
                    try:
                        self.wfile.write(json.dumps(resp_data).encode("utf-8"))
                    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                        pass
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                pass
            except Exception as e:
                try:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(f"Error: {e}".encode("utf-8"))
                except Exception: pass
        else:
            self.send_error(404, "Not Found")

class EmbeddedWeb2APIServer:
    def __init__(self, port=8081):
        self.port = port
        self.server = None
        self.thread = None

    def is_port_in_use(self):
        import urllib.request
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/models")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        return False

    def start(self):
        if self.server or self.is_port_in_use():
            return
        try:
            socketserver.TCPServer.allow_reuse_address = True
            self.server = socketserver.TCPServer(("127.0.0.1", self.port), Web2APIHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            logger.info("[Web2API Server] Started stealth background server on http://127.0.0.1:%s", self.port)
        except Exception as e:
            logger.warning("[Web2API Server] Notice starting port %s: %s", self.port, e)

    def stop(self):
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
                logger.info("[Web2API Server] Terminated stealth background server on port %s", self.port)
            except Exception as e:
                logger.warning("[Web2API Server] Error stopping server: %s", e)
            finally:
                self.server = None
                self.thread = None
