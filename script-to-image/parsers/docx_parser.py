"""
Word Document Script Parser
============================
Parses a .docx screenplay into the Script / Scene / ScriptLine model.

Handles two common Word screenplay formats:

Format A — Standard Fountain-style in Word
  - Scene headings: paragraph text starting with INT. / EXT.
  - Character names: ALL-CAPS paragraphs (optionally bold/centered)
  - Dialog: paragraph following a character name
  - Action: any other paragraph

Format B — Table-based scripts
  - Each row: | Scene | Character | Dialog | Emotion |
  - First row is treated as header and skipped

Usage
─────
    from parsers.docx_parser import DocxParser

    script = DocxParser().parse("my_script.docx")
    # or from bytes (Streamlit upload)
    script = DocxParser().parse_bytes(file_bytes, filename="script.docx")
"""

import io
import re
from pathlib import Path
from typing import Optional

from models.script import Script, Scene, ScriptLine


class DocxParser:

    def parse(self, path: str) -> Script:
        """Parse a .docx file at the given path."""
        try:
            from docx import Document
        except ImportError as e:
            raise ImportError("python-docx required: pip install python-docx") from e

        doc = Document(path)
        title = Path(path).stem
        return self._parse_document(doc, title)

    def parse_bytes(self, data: bytes, filename: str = "script.docx") -> Script:
        """Parse a .docx from raw bytes (e.g. Streamlit UploadedFile.read())."""
        try:
            from docx import Document
        except ImportError as e:
            raise ImportError("python-docx required: pip install python-docx") from e

        doc = Document(io.BytesIO(data))
        title = Path(filename).stem
        return self._parse_document(doc, title)

    # ------------------------------------------------------------------
    # Core parser
    # ------------------------------------------------------------------

    def _parse_document(self, doc, title: str) -> Script:
        # Detect table-based format
        if doc.tables:
            for table in doc.tables:
                result = self._try_parse_table(table, title)
                if result:
                    return result

        # Paragraph-based format
        return self._parse_paragraphs(doc, title)

    # ------------------------------------------------------------------
    # Paragraph-based parsing
    # ------------------------------------------------------------------

    def _parse_paragraphs(self, doc, title: str) -> Script:
        scenes: list[Scene] = []
        current_scene: Optional[Scene] = None
        scene_counter = 0
        last_character: Optional[str] = None
        dialog_buffer: list[str] = []

        def _flush_dialog():
            nonlocal dialog_buffer, last_character
            if dialog_buffer and last_character and current_scene is not None:
                current_scene.lines.append(ScriptLine(
                    type="dialog",
                    character=last_character,
                    text=" ".join(dialog_buffer).strip(),
                ))
            dialog_buffer = []
            last_character = None

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # ── Scene heading ──────────────────────────────────────────
            if self._is_scene_heading(para, text):
                _flush_dialog()
                if current_scene:
                    scenes.append(current_scene)
                scene_counter += 1
                location, tod = self._parse_heading(text)
                current_scene = Scene(
                    id=f"scene_{scene_counter:02d}",
                    location=location,
                    time_of_day=tod,
                )
                current_scene.lines.append(
                    ScriptLine(type="scene_heading", text=text)
                )
                continue

            if current_scene is None:
                # Text before first scene heading — treat as title
                continue

            # ── Character name ─────────────────────────────────────────
            if self._is_character_name(para, text):
                _flush_dialog()
                char_name = self._clean_character_name(text)
                last_character = char_name
                if char_name not in current_scene.characters:
                    current_scene.characters.append(char_name)
                continue

            # ── Parenthetical ──────────────────────────────────────────
            if text.startswith("(") and text.endswith(")") and last_character:
                # Emotion hint — attach to next dialog line
                continue

            # ── Dialog continuation ────────────────────────────────────
            if last_character:
                dialog_buffer.append(text)
                continue

            # ── Action / description ───────────────────────────────────
            _flush_dialog()
            current_scene.lines.append(ScriptLine(type="action", text=text))

        # Flush remaining
        _flush_dialog()
        if current_scene:
            scenes.append(current_scene)

        # If no scenes found, wrap everything as one scene
        if not scenes:
            scenes = self._fallback_single_scene(doc)

        scr = Script(title=title)
        scr.scenes = scenes
        return scr

    # ------------------------------------------------------------------
    # Table-based parsing
    # ------------------------------------------------------------------

    def _try_parse_table(self, table, title: str) -> Optional[Script]:
        """
        Handles tables where columns are:
        Scene | Character | Dialog | Emotion  (any order, detected from header row)
        """
        if len(table.rows) < 2:
            return None

        header = [c.text.strip().lower() for c in table.rows[0].cells]

        def _col(names):
            for n in names:
                for i, h in enumerate(header):
                    if n in h:
                        return i
            return None

        col_scene   = _col(["scene", "location", "int", "ext"])
        col_char    = _col(["character", "char", "speaker", "who"])
        col_dialog  = _col(["dialog", "dialogue", "line", "text", "speech"])
        col_emotion = _col(["emotion", "tone", "mood", "feeling"])

        if col_dialog is None:
            return None  # not a dialog table

        scenes: dict[str, Scene] = {}
        scene_counter = 0
        row_counter = 1

        for row in table.rows[1:]:
            cells = [c.text.strip() for c in row.cells]
            if not any(cells):
                continue

            scene_label = cells[col_scene].strip() if col_scene is not None and col_scene < len(cells) else ""
            character   = cells[col_char].strip()  if col_char  is not None and col_char  < len(cells) else ""
            dialog_text = cells[col_dialog].strip() if col_dialog < len(cells) else ""
            emotion     = cells[col_emotion].strip() if col_emotion is not None and col_emotion < len(cells) else ""

            if not dialog_text:
                continue

            # Create / find scene
            scene_key = scene_label or "scene_01"
            if scene_key not in scenes:
                scene_counter += 1
                location, tod = self._parse_heading(scene_label) if scene_label else (scene_label, "")
                sc = Scene(
                    id=f"scene_{scene_counter:02d}",
                    location=location or f"scene_{scene_counter:02d}",
                    time_of_day=tod,
                )
                scenes[scene_key] = sc

            sc = scenes[scene_key]
            if character and character not in sc.characters:
                sc.characters.append(character)

            sc.lines.append(ScriptLine(
                type="dialog",
                character=character or None,
                text=dialog_text,
                emotion=emotion or None,
            ))
            row_counter += 1

        if not scenes:
            return None

        scr = Script(title=title)
        scr.scenes = list(scenes.values())
        return scr

    # ------------------------------------------------------------------
    # Fallback — no scene headings found
    # ------------------------------------------------------------------

    def _fallback_single_scene(self, doc) -> list[Scene]:
        """Treat whole document as one scene, detect dialog by ALL-CAPS lines."""
        scene = Scene(id="scene_01", location="unknown")
        last_char = None
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            if self._is_character_name(para, text):
                last_char = self._clean_character_name(text)
                if last_char not in scene.characters:
                    scene.characters.append(last_char)
            elif last_char:
                scene.lines.append(ScriptLine(type="dialog", character=last_char, text=text))
                last_char = None
            else:
                scene.lines.append(ScriptLine(type="action", text=text))
        return [scene]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_scene_heading(self, para, text: str) -> bool:
        upper = text.upper()
        if re.match(r"^(INT\.|EXT\.|INT/EXT\.|I/E\.)\s", upper):
            return True
        # Bold + all-caps line that looks like a heading
        if self._is_bold(para) and upper == text and len(text) > 5 and len(text.split()) <= 8:
            if any(kw in upper for kw in ["SCENE", "INT", "EXT", "INTERIOR", "EXTERIOR"]):
                return True
        return False

    def _is_character_name(self, para, text: str) -> bool:
        if not text or len(text) > 50:
            return False
        # All caps, no punctuation (except apostrophe/hyphen), short
        cleaned = re.sub(r"['\-\s]", "", text)
        if cleaned.isupper() and 2 <= len(text.split()) <= 4:
            return True
        # Bold + title case short phrase
        if self._is_bold(para) and text.istitle() and len(text.split()) <= 3:
            return True
        return False

    def _is_bold(self, para) -> bool:
        return any(run.bold for run in para.runs if run.text.strip())

    def _clean_character_name(self, text: str) -> str:
        # Remove parentheticals like "(V.O.)" "(O.S.)"
        return re.sub(r"\s*\(.*?\)", "", text).strip().title()

    def _parse_heading(self, text: str):
        """Extract location and time-of-day from a scene heading."""
        text = re.sub(r"^(INT\.|EXT\.|INT/EXT\.|I/E\.)\s*", "", text,
                      flags=re.IGNORECASE).strip()
        parts = re.split(r"\s*[-–—]\s*", text, maxsplit=1)
        location = parts[0].strip().lower() if parts else text.lower()
        tod = parts[1].strip() if len(parts) > 1 else ""
        return location, tod
