from PIL import Image

try:
    import pytesseract
except ImportError:
    pytesseract = None


class OCRProcessor:
    def extract_text(self, path: str) -> str:
        if pytesseract is None:
            return ""
        try:
            with Image.open(path) as img:
                return pytesseract.image_to_string(img, lang="tur+eng").strip()
        except Exception:
            pass
        try:
            with Image.open(path) as img:
                return pytesseract.image_to_string(img).strip()
        except Exception:
            return ""
