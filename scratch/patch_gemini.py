import codecs

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

text = text.replace('text_response = response.text', 'text_response = self._extract_gemini_text(response)')
text = text.replace('text_response = f"⚠️ *[Groq Error: Fell back to Gemini]*\\n\\n" + response.text', 'text_response = f"⚠️ *[Groq Error: Fell back to Gemini]*\\n\\n" + self._extract_gemini_text(response)')
text = text.replace('text_response = f"⚠️ *[OpenRouter Error: Fell back to Gemini]*\\n\\n" + response.text', 'text_response = f"⚠️ *[OpenRouter Error: Fell back to Gemini]*\\n\\n" + self._extract_gemini_text(response)')

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Patched successfully.")
