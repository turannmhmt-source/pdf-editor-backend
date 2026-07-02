# AI PDF Editör

## Kurulum

```bash
pip install -r requirements.txt
cp .env.example .env   # GROQ_API_KEY ve/veya OPENAI_API_KEY değerlerini gir
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Render Ayarları

- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Environment Variables:** `GROQ_API_KEY`, `OPENAI_API_KEY`

En az bir API anahtarı (Groq veya OpenAI) tanımlı olmalı; aksi halde komut yorumlama ve sesli komut çevirisi çalışmaz.

## OCR (opsiyonel görsel yükleme özelliği)

Görsel üzerinden OCR, sistemde `tesseract-ocr` (ve Türkçe için `tesseract-ocr-tur`) paketinin kurulu olmasını gerektirir. Render'ın standart Python ortamında bu paket bulunmaz; gerekiyorsa Docker tabanlı bir servis kullanılmalıdır. Tesseract kurulu değilse OCR sessizce boş sonuç döner, PDF yükleme ve düzenleme özellikleri bundan etkilenmez.
