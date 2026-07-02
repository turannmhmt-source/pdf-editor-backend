import fitz  # PyMuPDF


class PDFProcessor:
    def extract_text(self, path: str) -> str:
        with fitz.open(path) as doc:
            return "\n".join(page.get_text() for page in doc)

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
            self._find_replace(doc, str(action.get("find", "")), str(action.get("replace", "")))
        elif action_type == "add_text":
            self._add_text(doc, action)

    def _find_replace(self, doc, find: str, replace: str) -> None:
        if not find:
            return
        fontname = "helv"
        for page in doc:
            rects = page.search_for(find)
            if not rects:
                continue
            for rect in rects:
                page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()
            for rect in rects:
                fontsize = max(rect.height - 2, 6)
                if replace:
                    text_width = fitz.get_text_length(replace, fontname=fontname, fontsize=fontsize)
                    if text_width > rect.width:
                        fontsize = max(fontsize * (rect.width / text_width), 4)
                page.insert_text((rect.x0, rect.y1 - 2), replace, fontsize=fontsize, fontname=fontname)

    def _add_text(self, doc, action: dict) -> None:
        text = str(action.get("text", ""))
        if not text:
            return
        page_num = int(action.get("page", 0) or 0)
        if page_num < 0 or page_num >= len(doc):
            page_num = 0
        page = doc[page_num]
        x = float(action.get("x", 50))
        y = float(action.get("y", 50))
        fontsize = float(action.get("fontsize", 12))
        page.insert_text((x, y), text, fontsize=fontsize)
