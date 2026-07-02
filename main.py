import os, re, uuid, shutil
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from pdf_processor import PDFProcessor
from ai_interpreter import AIInterpreter
from ocr_processor import OCRProcessor

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY","")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY","")

UPLOAD_DIR = Path("uploads"); RESULT_DIR = Path("results")
UPLOAD_DIR.mkdir(exist_ok=True); RESULT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="AI PDF Editör")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

pdf_proc = PDFProcessor()
ai_interp = AIInterpreter(GROQ_API_KEY, OPENAI_API_KEY)
ocr_proc = OCRProcessor()

if Path("static").exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

_ID_RE = re.compile(r"^[0-9a-f]{32}$")

def _is_valid_id(value: str) -> bool:
    return bool(value) and bool(_ID_RE.match(value))

class CommandRequest(BaseModel):
    pdf_id: str
    command: str
    image_id: str = ""

@app.get("/")
async def root():
    p = Path("static/index.html")
    return FileResponse(str(p)) if p.exists() else {"status":"ok"}

@app.get("/health")
async def health():
    return {"status":"ok","groq":bool(GROQ_API_KEY),"openai":bool(OPENAI_API_KEY)}

@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Sadece PDF dosyaları yüklenebilir.")
    pid = uuid.uuid4().hex
    dest = UPLOAD_DIR/f"{pid}.pdf"
    try:
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception:
        dest.unlink(missing_ok=True)
        raise HTTPException(500, "PDF dosyası kaydedilirken bir hata oluştu. Lütfen tekrar deneyin.")
    finally:
        await file.close()
    if dest.stat().st_size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "Yüklenen PDF dosyası boş görünüyor. Lütfen geçerli bir dosya seçin.")
    return {"pdf_id":pid,"filename":file.filename}

@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in [".jpg",".jpeg",".png",".webp",".bmp"]:
        raise HTTPException(400,"Desteklenmeyen görsel formatı. Lütfen jpg, jpeg, png, webp veya bmp yükleyin.")
    iid = uuid.uuid4().hex
    dest = UPLOAD_DIR/f"{iid}{ext}"
    try:
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception:
        dest.unlink(missing_ok=True)
        raise HTTPException(500, "Görsel kaydedilirken bir hata oluştu. Lütfen tekrar deneyin.")
    finally:
        await file.close()
    if dest.stat().st_size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "Yüklenen görsel boş görünüyor. Lütfen geçerli bir dosya seçin.")
    return {"image_id":iid,"filename":file.filename}

@app.post("/voice-to-text")
async def voice_to_text(file: UploadFile = File(...)):
    aid = uuid.uuid4().hex
    ext = Path(file.filename).suffix if file.filename else ".webm"
    p = UPLOAD_DIR/f"{aid}{ext}"
    try:
        with open(p, "wb") as f:
            shutil.copyfileobj(file.file, f)
        text = ai_interp.transcribe_audio(str(p))
    except Exception:
        raise HTTPException(500, "Ses metne çevrilirken bir hata oluştu. Lütfen tekrar deneyin.")
    finally:
        await file.close()
        p.unlink(missing_ok=True)
    return {"text":text}

@app.post("/process-command")
async def process_command(req: CommandRequest):
    if not req.command.strip():
        raise HTTPException(400, "Lütfen bir komut girin.")
    if not _is_valid_id(req.pdf_id):
        raise HTTPException(400, "Geçersiz PDF kimliği. Lütfen dosyayı tekrar yükleyin.")
    pdf_path = UPLOAD_DIR/f"{req.pdf_id}.pdf"
    if not pdf_path.exists(): raise HTTPException(404,"PDF bulunamadı. Lütfen dosyayı tekrar yükleyin.")
    pdf_text = pdf_proc.extract_text(str(pdf_path))
    ocr_text = ""
    if req.image_id and _is_valid_id(req.image_id):
        for ext in [".jpg",".jpeg",".png",".webp",".bmp"]:
            ip = UPLOAD_DIR/f"{req.image_id}{ext}"
            if ip.exists():
                ocr_text = ocr_proc.extract_text(str(ip))
                if not ocr_text:
                    ocr_text = ai_interp.read_image_text(str(ip))
                break
    actions = ai_interp.interpret_command(pdf_text, req.command, ocr_text)
    if not actions: raise HTTPException(422,"Komut anlaşılamadı. Lütfen komutunuzu daha açık bir şekilde yazın.")
    rid = uuid.uuid4().hex
    rp = RESULT_DIR/f"{rid}.pdf"
    if not pdf_proc.apply_actions(str(pdf_path), actions, str(rp)) or not rp.exists():
        raise HTTPException(500,"PDF düzenlenemedi. Lütfen komutunuzu kontrol edip tekrar deneyin.")
    return {"result_id":rid,"actions_applied":actions,"download_url":f"/download-pdf/{rid}"}

@app.get("/download-pdf/{result_id}")
async def download_pdf(result_id: str):
    if not _is_valid_id(result_id): raise HTTPException(404,"Dosya bulunamadı.")
    p = RESULT_DIR/f"{result_id}.pdf"
    if not p.exists(): raise HTTPException(404,"Dosya bulunamadı.")
    return FileResponse(str(p), media_type="application/pdf", filename=f"duzenlenmis_{result_id[:8]}.pdf")
