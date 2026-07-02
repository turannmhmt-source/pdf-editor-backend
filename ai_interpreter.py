import json
import re

_ACTION_TYPES = {"find_replace", "add_text"}


class AIInterpreter:
    def __init__(self, groq_api_key: str = "", openai_api_key: str = ""):
        self._groq_client = None
        self._openai_client = None
        if groq_api_key:
            try:
                from groq import Groq
                self._groq_client = Groq(api_key=groq_api_key)
            except Exception:
                self._groq_client = None
        if openai_api_key:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=openai_api_key)
            except Exception:
                self._openai_client = None

    def transcribe_audio(self, path: str) -> str:
        if self._groq_client:
            try:
                with open(path, "rb") as f:
                    result = self._groq_client.audio.transcriptions.create(
                        file=f, model="whisper-large-v3", language="tr"
                    )
                return (result.text or "").strip()
            except Exception:
                pass
        if self._openai_client:
            try:
                with open(path, "rb") as f:
                    result = self._openai_client.audio.transcriptions.create(
                        file=f, model="whisper-1", language="tr"
                    )
                return (result.text or "").strip()
            except Exception:
                pass
        return ""

    def interpret_command(self, pdf_text: str, command: str, ocr_text: str = "") -> list:
        prompt = self._build_prompt(pdf_text, command, ocr_text)
        raw = self._call_llm(prompt)
        return self._parse_actions(raw)

    def _build_prompt(self, pdf_text: str, command: str, ocr_text: str) -> str:
        extra = f"\nReferans görselden okunan metin:\n{ocr_text[:2000]}" if ocr_text else ""
        return (
            "Aşağıda bir PDF belgesinin metni ve kullanıcının bu belge üzerinde yapılmasını "
            "istediği bir komut var. Bu komutu, aşağıdaki JSON şemasına uyan bir eylem listesine çevir.\n\n"
            "Desteklenen eylem tipleri:\n"
            '- {"type": "find_replace", "find": "<bulunacak metin>", "replace": "<yeni metin>"}\n'
            '- {"type": "add_text", "page": <sayfa no, 0 tabanlı>, "x": <x>, "y": <y>, '
            '"text": "<eklenecek metin>", "fontsize": <punto>}\n\n'
            "Kurallar:\n"
            "- Sadece geçerli bir JSON dizisi döndür, başka hiçbir açıklama ya da metin yazma.\n"
            "- Komutu uygulamak mümkün değilse boş dizi [] döndür.\n\n"
            f"PDF metni:\n{pdf_text[:6000]}{extra}\n\n"
            f"Kullanıcı komutu: {command}\n\n"
            "JSON:"
        )

    def _call_llm(self, prompt: str) -> str:
        if self._groq_client:
            try:
                resp = self._groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                )
                return resp.choices[0].message.content or ""
            except Exception:
                pass
        if self._openai_client:
            try:
                resp = self._openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                )
                return resp.choices[0].message.content or ""
            except Exception:
                pass
        return ""

    def _parse_actions(self, raw: str) -> list:
        if not raw:
            return []
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []
        try:
            actions = json.loads(match.group(0))
        except Exception:
            return []
        if not isinstance(actions, list):
            return []
        return [a for a in actions if isinstance(a, dict) and a.get("type") in _ACTION_TYPES]
