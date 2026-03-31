"""
Google Sheets Exporter
======================
Exports a Script to a Google Sheet (or CSV) with one row per dialog / action line.

Sheet columns
─────────────
 A  Row          sequential number
 B  Scene ID     scene_01 / scene_02 …
 C  Scene #      1 / 2 / 3 …
 D  Location     neon alley
 E  Time of Day  midnight
 F  Characters   Elena, Marcus  (everyone present in the scene)
 G  Line #       position within the scene
 H  Type         DIALOG / ACTION / SCENE HEADING
 I  Character    speaker name (dialog rows only)
 J  Line / Text  the dialog or action text
 K  Emotion      threatening, tired …
 L  Gen Image?   YES / —
 M  Image Prompt (blank — filled later by PromptGenerator or manually)
 N  Notes        (blank — for production notes)

Google Sheets auth
──────────────────
Two options, tried in order:
  1. Service-account JSON  →  set GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/sa.json
  2. OAuth browser flow    →  set GOOGLE_OAUTH_CREDENTIALS=/path/to/credentials.json
                              (opens browser on first run, caches token)
If neither is set the exporter falls back to CSV-only mode.

Usage
─────
    from generators.sheets_exporter import SheetsExporter
    from models.script import Script

    script = Script.from_json_file("examples/sample_script.json")

    exp = SheetsExporter()

    # Export to Google Sheets
    url = exp.to_google_sheets(script, title="Ghost Signal — Production")
    print("Sheet URL:", url)

    # Export to CSV (always available, no API key needed)
    csv_path = exp.to_csv(script, path="output/ghost_signal.csv")
"""

import csv
import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from models.script import Script, Scene, ScriptLine


# ---------------------------------------------------------------------------
# Per-character colour palette (Google Sheets RGB hex)
# Applied to dialog rows so each character has a distinct background tint.
# ---------------------------------------------------------------------------
CHARACTER_COLORS = [
    "#D0E8FF",  # blue
    "#D5F5E3",  # green
    "#FAD7A0",  # orange
    "#E8DAEF",  # lavender
    "#FDEBD0",  # peach
    "#D6EAF8",  # sky
    "#FDEDEC",  # rose
    "#E9F7EF",  # mint
]

HEADER_BG    = "#1A1A2E"
HEADER_FG    = "#FFFFFF"
ACTION_BG    = "#F2F3F4"
SCENE_HDR_BG = "#2C3E50"
SCENE_HDR_FG = "#ECF0F1"

COLUMNS = [
    "Row", "Scene ID", "Scene #", "Location", "Time of Day",
    "Characters in Scene", "Line #", "Type", "Character",
    "Dialog / Action Text", "Emotion / Tone", "Gen Image?",
    "Image Prompt", "Notes",
]


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

@dataclass
class SheetRow:
    row_num: int
    scene_id: str
    scene_num: int
    location: str
    time_of_day: str
    characters_in_scene: str
    line_num: int
    line_type: str        # DIALOG / ACTION / SCENE HEADING
    character: str
    text: str
    emotion: str
    gen_image: str        # YES / —
    image_prompt: str = ""
    notes: str = ""

    def as_list(self) -> list:
        return [
            self.row_num, self.scene_id, self.scene_num,
            self.location, self.time_of_day, self.characters_in_scene,
            self.line_num, self.line_type, self.character,
            self.text, self.emotion, self.gen_image,
            self.image_prompt, self.notes,
        ]


def _build_rows(script: Script) -> list[SheetRow]:
    """Flatten Script → list of SheetRow, one per line."""
    rows = []
    row_num = 1

    for scene_num, scene in enumerate(script.scenes, start=1):
        chars_str = ", ".join(scene.characters)
        tod = scene.time_of_day or ""

        for line_num, line in enumerate(scene.lines, start=1):
            line_type = line.type.upper().replace("_", " ")
            rows.append(SheetRow(
                row_num=row_num,
                scene_id=scene.id,
                scene_num=scene_num,
                location=scene.location,
                time_of_day=tod,
                characters_in_scene=chars_str,
                line_num=line_num,
                line_type=line_type,
                character=line.character or "",
                text=line.text,
                emotion=line.emotion or "",
                gen_image="YES" if line.generate_image else "—",
            ))
            row_num += 1

    return rows


# ---------------------------------------------------------------------------
# CSV exporter (always available — no API key required)
# ---------------------------------------------------------------------------

class SheetsExporter:
    """
    Exports a Script to Google Sheets or CSV.
    Google Sheets requires gspread + a service-account or OAuth credential.
    CSV mode always works with no dependencies.
    """

    def to_csv(self, script: Script, path: Optional[str] = None) -> Path:
        """
        Write script rows to a CSV file.
        If path is None, writes to output/<title>.csv.
        Returns the Path of the saved file.
        """
        if path is None:
            out_dir = Path("output")
            out_dir.mkdir(exist_ok=True)
            safe_title = script.title.replace(" ", "_").replace("/", "-")
            path = str(out_dir / f"{safe_title}_script.csv")

        rows = _build_rows(script)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)
            for r in rows:
                writer.writerow(r.as_list())

        return Path(path)

    def to_csv_bytes(self, script: Script) -> bytes:
        """Return CSV content as bytes (for Streamlit download_button)."""
        rows = _build_rows(script)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(COLUMNS)
        for r in rows:
            writer.writerow(r.as_list())
        return buf.getvalue().encode("utf-8")

    # ------------------------------------------------------------------
    # Google Sheets exporter
    # ------------------------------------------------------------------

    def to_google_sheets(
        self,
        script: Script,
        title: Optional[str] = None,
        share_with: Optional[str] = None,   # email to share the sheet with
        service_account_json: Optional[str] = None,
        oauth_credentials: Optional[str] = None,
    ) -> str:
        """
        Create (or overwrite) a Google Sheet for the script.
        Returns the URL of the created spreadsheet.

        Auth priority:
          1. service_account_json  parameter
          2. GOOGLE_SERVICE_ACCOUNT_JSON  env var  (path to JSON file)
          3. oauth_credentials  parameter
          4. GOOGLE_OAUTH_CREDENTIALS  env var  (path to credentials.json)
        """
        gc = self._auth(service_account_json, oauth_credentials)
        sheet_title = title or f"{script.title} — Script Breakdown"
        rows = _build_rows(script)

        # Create spreadsheet
        spreadsheet = gc.create(sheet_title)
        ws = spreadsheet.sheet1
        ws.update_title("Script")

        # Write header + data in one batch call
        all_values = [COLUMNS] + [r.as_list() for r in rows]
        ws.update("A1", all_values, value_input_option="USER_ENTERED")

        # Formatting
        self._format_sheet(ws, rows, spreadsheet.id, gc)

        # Share if requested
        if share_with:
            spreadsheet.share(share_with, perm_type="user", role="writer")

        return spreadsheet.url

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_sheet(self, ws, rows: list[SheetRow], spreadsheet_id: str, gc) -> None:
        """Apply colours, bold header, freeze, column widths."""
        try:
            import gspread
            from gspread.utils import rowcol_to_a1
            from gspread_formatting import (
                CellFormat, Color, TextFormat,
                format_cell_range, set_frozen,
                set_column_width,
            )
        except ImportError:
            return   # formatting is optional — skip silently

        # Build character → colour map
        all_chars = []
        for r in rows:
            if r.character and r.character not in all_chars:
                all_chars.append(r.character)
        char_color = {
            c: CHARACTER_COLORS[i % len(CHARACTER_COLORS)]
            for i, c in enumerate(all_chars)
        }

        def _hex_to_color(h: str) -> Color:
            h = h.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return Color(r / 255, g / 255, b / 255)

        # Header row
        header_fmt = CellFormat(
            backgroundColor=_hex_to_color(HEADER_BG),
            textFormat=TextFormat(
                bold=True, foregroundColor=_hex_to_color(HEADER_FG), fontSize=10
            ),
        )
        format_cell_range(ws, "A1:N1", header_fmt)

        # Data rows
        for i, row in enumerate(rows, start=2):
            cell_range = f"A{i}:N{i}"

            if row.line_type == "SCENE HEADING":
                fmt = CellFormat(
                    backgroundColor=_hex_to_color(SCENE_HDR_BG),
                    textFormat=TextFormat(
                        bold=True, foregroundColor=_hex_to_color(SCENE_HDR_FG)
                    ),
                )
            elif row.line_type == "ACTION":
                fmt = CellFormat(backgroundColor=_hex_to_color(ACTION_BG))
            elif row.character and row.character in char_color:
                fmt = CellFormat(
                    backgroundColor=_hex_to_color(char_color[row.character])
                )
            else:
                continue   # default white

            format_cell_range(ws, cell_range, fmt)

        # Freeze header row
        set_frozen(ws, rows=1)

        # Column widths (col index is 1-based)
        widths = {
            1: 50,   # Row
            2: 90,   # Scene ID
            3: 70,   # Scene #
            4: 130,  # Location
            5: 120,  # Time of Day
            6: 160,  # Characters
            7: 60,   # Line #
            8: 110,  # Type
            9: 110,  # Character
            10: 350, # Dialog Text
            11: 160, # Emotion
            12: 90,  # Gen Image
            13: 300, # Image Prompt
            14: 180, # Notes
        }
        for col, width in widths.items():
            try:
                set_column_width(ws, col, width)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _auth(
        self,
        service_account_json: Optional[str],
        oauth_credentials: Optional[str],
    ):
        """Return an authenticated gspread client."""
        try:
            import gspread
        except ImportError as e:
            raise ImportError(
                "gspread is required for Google Sheets export. "
                "Install it with: pip install gspread gspread-formatting"
            ) from e

        # 1. Service account JSON file path
        sa_path = service_account_json or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if sa_path and Path(sa_path).exists():
            return gspread.service_account(filename=sa_path)

        # 2. Service account JSON string (inline)
        sa_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT")
        if sa_json_str:
            import json, tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                f.write(sa_json_str)
                tmp_path = f.name
            return gspread.service_account(filename=tmp_path)

        # 3. OAuth credentials
        oauth_path = oauth_credentials or os.environ.get("GOOGLE_OAUTH_CREDENTIALS")
        if oauth_path and Path(oauth_path).exists():
            return gspread.oauth(credentials_filename=oauth_path)

        raise ValueError(
            "No Google credentials found.\n"
            "Set one of:\n"
            "  GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/sa.json\n"
            "  GOOGLE_OAUTH_CREDENTIALS=/path/to/credentials.json\n"
            "or pass service_account_json= / oauth_credentials= directly."
        )
