import base64
import json
import re
from pathlib import Path

_ACTION_TYPES = {"find_replace", "add_text"}
_IMAGE_READ_PROMPT = (
    "Bu görseldeki (kimlik, pasaport, fatura vb.) tüm okunabilir metni olduğu gibi "
    "çıkar. İsim, soyisim, numara, tarih gibi tüm alanları eksiksiz ve satır satır "
    "yaz. Sadece görselde gördüğün metni yaz, yorum veya açıklama ekleme."
)


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

    def read_image_text(self, path: str) -> str:
        try:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
        except Exception:
            return ""
        ext = Path(path).suffix.lower().lstrip(".") or "jpeg"
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        data_url = f"data:{mime};base64,{b64}"
        content = [
            {"type": "text", "text": _IMAGE_READ_PROMPT},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
        if self._groq_client:
            try:
                resp = self._groq_client.chat.completions.create(
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    messages=[{"role": "user", "content": content}],
                    temperature=0,
                )
                text = (resp.choices[0].message.content or "").strip()
                if text:
                    return text
            except Exception:
                pass
        if self._openai_client:
            try:
                resp = self._openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": content}],
                    temperature=0,
                )
                return (resp.choices[0].message.content or "").strip()
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
            "istediği bir komut var. PDF metni, her sayfanın başında [Sayfa N] işaretiyle "
            "ayrılmış şekilde verilmiştir. Bu komutu, aşağıdaki JSON şemasına uyan bir eylem "
            "listesine çevir.\n\n"
            "Desteklenen eylem tipleri:\n"
            '- {"type": "find_replace", "find": "<bulunacak metin>", "replace": "<yeni metin>", '
            '"page": <opsiyonel, 1 tabanlı sayfa no>, "occurrence": <opsiyonel, kaçıncı '
            'eşleşme, 1 tabanlı>}\n'
            '- {"type": "add_text", "page": <1 tabanlı sayfa no>, "x": <x>, "y": <y>, '
            '"text": "<eklenecek metin>", "fontsize": <punto>}\n\n'
            "Kurallar:\n"
            "- \"find\" alanı PDF metninde birebir (karakteri karakterine) geçen bir metin "
            "olmalı. Sadece komutta geçen kelimeyi değil, PDF metnindeki gerçek yazımını kullan.\n"
            "- \"find\" için mümkün olduğunca uzun ve benzersiz bir metin parçası seç; gerekirse "
            "hemen öncesindeki/sonrasındaki kelimeleri de dahil et. Tek başına belgede başka "
            "yerlerde de geçebilecek kısa/genel ifadeler (örn. sadece bir sayı veya yaygın bir "
            "kelime) seçme — aksi halde belgede istenmeyen başka yerler de değişebilir.\n"
            "- Değiştirilecek metnin hangi sayfada olduğu PDF metnindeki [Sayfa N] işaretinden "
            "belliyse, \"page\" alanını mutlaka doldur.\n"
            "- Aynı metin PDF'te birden fazla yerde geçiyorsa ve kullanıcı sadece belirli birini "
            "kastediyorsa (örn. \"ilk\", \"ikinci\" gibi), \"occurrence\" alanını kullan; "
            "kullanıcı tüm eşleşmelerin değişmesini istiyorsa (örn. bir ismin her geçtiği yer) "
            "\"occurrence\" ve \"page\" alanlarını boş bırak.\n"
            "- Sadece geçerli bir JSON dizisi döndür, başka hiçbir açıklama ya da metin yazma.\n"
            "- Komutu uygulamak mümkün değilse veya \"find\" metnini PDF metninde bulamıyorsan "
            "boş dizi [] döndür, tahmin yürütme.\n\n"
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
