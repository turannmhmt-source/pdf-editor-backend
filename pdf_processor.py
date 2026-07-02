from pathlib import Path
import fitz  # PyMuPDF

FONT_DIR = Path(__file__).parent / "fonts"

# Base-14 fonts (helv/Helvetica, Times-Roman, Courier...) lack Turkish glyphs
# (İ, ı, Ş, ş, Ğ, ğ...), so all text we write into the PDF uses one of these
# embedded Unicode fonts instead, picked to visually match the original text
# (serif/sans/monospace, bold, italic).
FONT_FILES = {
    ("sans", False, False): FONT_DIR / "LiberationSans-Regular.ttf",
    ("sans", True, False): FONT_DIR / "LiberationSans-Bold.ttf",
    ("sans", False, True): FONT_DIR / "LiberationSans-Italic.ttf",
    ("sans", True, True): FONT_DIR / "LiberationSans-BoldItalic.ttf",
    ("serif", False, False): FONT_DIR / "LiberationSerif-Regular.ttf",
    ("serif", True, False): FONT_DIR / "LiberationSerif-Bold.ttf",
    ("serif", False, True): FONT_DIR / "LiberationSerif-Italic.ttf",
    ("serif", True, True): FONT_DIR / "LiberationSerif-BoldItalic.ttf",
    ("mono", False, False): FONT_DIR / "LiberationMono-Regular.ttf",
    ("mono", True, False): FONT_DIR / "LiberationMono-Bold.ttf",
    ("mono", False, True): FONT_DIR / "LiberationMono-Italic.ttf",
    ("mono", True, True): FONT_DIR / "LiberationMono-BoldItalic.ttf",
}
DEFAULT_FONT_KEY = ("sans", False, False)

FLAG_SERIF = 1 << 2
FLAG_MONOSPACE = 1 << 3
FLAG_BOLD = 1 << 4
FLAG_ITALIC = 1 << 1


class PDFProcessor:
    def __init__(self):
        self._fonts = {key: fitz.Font(fontfile=str(path)) for key, path in FONT_FILES.items()}

    def extract_text(self, path: str) -> str:
        with fitz.open(path) as doc:
            pages = [f"[Sayfa {i + 1}]\n{page.get_text()}" for i, page in enumerate(doc)]
            return "\n".join(pages)

    def apply_actions(self, path: str, actions: list, output_path: str) -> bool:
        try:
            with fitz.open(path) as doc:
                for action in actions:
                    self._apply_action(doc, action)
                doc.save(output_path)
            return True
        except Exception:
            return False

    def _apply_action(self, doc, action: dict) -> None:
        action_type = action.get("type")
        if action_type == "find_replace":
            self._find_replace(doc, action)
        elif action_type == "add_text":
            self._add_text(doc, action)

    @staticmethod
    def _to_int(value):
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    def _font_key(self, span: dict) -> tuple:
        name = (span.get("font") or "").lower()
        flags = span.get("flags", 0)
        if "courier" in name or "mono" in name or "consolas" in name or flags & FLAG_MONOSPACE:
            family = "mono"
        elif "times" in name or "serif" in name or "georgia" in name or "cambria" in name or flags & FLAG_SERIF:
            family = "serif"
        else:
            family = "sans"
        bold = "bold" in name or bool(flags & FLAG_BOLD)
        italic = "italic" in name or "oblique" in name or bool(flags & FLAG_ITALIC)
        return (family, bold, italic)

    def _color_tuple(self, color_int) -> tuple:
        if not isinstance(color_int, int):
            return (0, 0, 0)
        r = ((color_int >> 16) & 255) / 255
        g = ((color_int >> 8) & 255) / 255
        b = (color_int & 255) / 255
        return (r, g, b)

    def _span_at(self, page, rect: "fitz.Rect", point=None):
        cx, cy = point if point else ((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
        best = None
        best_dist = None
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    bbox = fitz.Rect(span["bbox"])
                    if bbox.contains((cx, cy)):
                        return span
                    scx, scy = (bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2
                    dist = (scx - cx) ** 2 + (scy - cy) ** 2
                    if best_dist is None or dist < best_dist:
                        best_dist = dist
                        best = span
        return best

    def _insert_matched_text(self, page, rect, span, text: str) -> None:
        key = self._font_key(span) if span else DEFAULT_FONT_KEY
        font = self._fonts[key]
        fontsize = float(span["size"]) if span and span.get("size") else max(rect.height - 2, 6)
        color = self._color_tuple(span.get("color")) if span else (0, 0, 0)
        if text:
            text_width = font.text_length(text, fontsize=fontsize)
            if text_width > rect.width:
                fontsize = max(fontsize * (rect.width / text_width), 4)
        page.insert_text(
            (rect.x0, rect.y1 - 2), text,
            fontsize=fontsize, fontname=f"f-{key[0]}-{int(key[1])}-{int(key[2])}",
            fontfile=str(FONT_FILES[key]), color=color,
        )

    def _find_replace(self, doc, action: dict) -> None:
        find = str(action.get("find", ""))
        replace = str(action.get("replace", ""))
        if not find:
            return
        page_filter = self._to_int(action.get("page"))
        occurrence = self._to_int(action.get("occurrence"))

        if page_filter and 1 <= page_filter <= len(doc):
            pages = [doc[page_filter - 1]]
        else:
            pages = list(doc)

        seen = 0
        for page in pages:
            rects = page.search_for(find)
            if not rects:
                continue
            if occurrence:
                target = []
                for rect in rects:
                    seen += 1
                    if seen == occurrence:
                        target = [rect]
                        break
                rects = target
                if not rects:
                    continue
            # Font info must be read before redaction removes the original text.
            spans = [self._span_at(page, rect) for rect in rects]
            for rect in rects:
                page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()
            for rect, span in zip(rects, spans):
                self._insert_matched_text(page, rect, span, replace)
            if occurrence:
                return

    def _add_text(self, doc, action: dict) -> None:
        text = str(action.get("text", ""))
        if not text:
            return
        page_num = self._to_int(action.get("page")) or 1
        page_num -= 1
        if page_num < 0 or page_num >= len(doc):
            page_num = 0
        page = doc[page_num]
        x = float(action.get("x", 50))
        y = float(action.get("y", 50))
        fontsize = float(action.get("fontsize", 12))
        nearby_span = self._span_at(page, fitz.Rect(x, y, x, y), point=(x, y))
        key = self._font_key(nearby_span) if nearby_span else DEFAULT_FONT_KEY
        page.insert_text(
            (x, y), text,
            fontsize=fontsize, fontname=f"f-{key[0]}-{int(key[1])}-{int(key[2])}",
            fontfile=str(FONT_FILES[key]),
        )
