"""
Scene Image Pusher
==================
After a Google Sheet has been created (Tab 1 = Script, Tab 2 = Character Canvas),
this module:
  1. Iterates through every dialog row in the Script tab
  2. Generates a cinematic image prompt per dialog (Claude)
  3. Builds a Pollinations.ai URL for the image (free, no API key)
  4. Writes both the prompt and an =IMAGE() formula back into the sheet

The result: every dialog row in Google Sheets shows its corresponding
AI-generated scene image right in the cell.

Usage
─────
    from generators.scene_image_pusher import SceneImagePusher

    pusher = SceneImagePusher(anthropic_api_key="sk-ant-...")
    count = pusher.run(
        spreadsheet_url="https://docs.google.com/spreadsheets/d/xxx",
        script=script,
        char_sheet=char_sheet,
        loc_sheet=loc_sheet,
        service_account_json="/path/to/sa.json",
    )
    print(f"Pushed {count} images")
"""

import os
import urllib.parse
from pathlib import Path
from typing import Optional

from models.character import CharacterSheet
from models.location import LocationSheet
from models.script import Script, Scene


# Column indices (1-based) in the "Script" worksheet
COL_ROW        = 1
COL_SCENE_ID   = 2
COL_TYPE       = 8
COL_CHARACTER  = 9
COL_TEXT       = 10
COL_EMOTION    = 11
COL_IMG_PROMPT = 13   # M
COL_IMG_URL    = 15   # O  (we add this column)


POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"


class SceneImagePusher:
    """
    Generates images for every dialog line and pushes the URL
    back into the Google Sheet's Script tab.
    """

    def __init__(
        self,
        anthropic_api_key: Optional[str] = None,
        pollinations_model: str = "flux",
        image_width: int = 1024,
        image_height: int = 576,
        seed: Optional[int] = 42,
    ):
        self._api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = pollinations_model
        self.width = image_width
        self.height = image_height
        self.seed = seed

    # ------------------------------------------------------------------
    # Build a stable Pollinations URL
    # ------------------------------------------------------------------

    def build_image_url(self, prompt: str) -> str:
        """
        Return a Pollinations.ai URL that serves the generated image.
        Using a fixed seed makes the URL deterministic.
        """
        encoded = urllib.parse.quote(prompt, safe="")
        params = (
            f"?width={self.width}&height={self.height}"
            f"&model={self.model}&nologo=true&enhance=false"
        )
        if self.seed is not None:
            params += f"&seed={self.seed}"
        return f"{POLLINATIONS_BASE}/{encoded}{params}"

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def run(
        self,
        spreadsheet_url: str,
        script: Script,
        char_sheet: CharacterSheet,
        loc_sheet: LocationSheet,
        service_account_json: Optional[str] = None,
        oauth_credentials: Optional[str] = None,
        skip_existing: bool = True,
        selected_scenes: Optional[list[str]] = None,   # None = all
        extra_style: str = "",
        on_progress=None,           # callback(current, total, label)
    ) -> int:
        """
        Full pipeline:
          1. Open the existing Google Sheet
          2. Ensure "Image URL" header exists (column O)
          3. For each DIALOG row → generate prompt → build image URL → update cells
          4. Skip rows that already have an image URL (if skip_existing=True)

        Returns the number of rows updated.
        """
        from generators.prompt_generator import PromptGenerator

        # Auth + open sheet
        gc = self._auth(service_account_json, oauth_credentials)
        spreadsheet = gc.open_by_url(spreadsheet_url)
        ws = spreadsheet.worksheet("Script")

        # Ensure column O header exists
        header_row = ws.row_values(1)
        if len(header_row) < COL_IMG_URL or header_row[COL_IMG_URL - 1] != "Image URL":
            ws.update_cell(1, COL_IMG_URL, "Image URL")

        # Read all data to determine which rows need images
        all_data = ws.get_all_values()
        total_rows = len(all_data) - 1  # minus header

        # Build scene lookup for context
        scene_map: dict[str, Scene] = {s.id: s for s in script.scenes}

        prompt_gen = PromptGenerator(api_key=self._api_key)

        updated = 0
        dialog_rows = []

        for row_idx in range(1, len(all_data)):  # 0-based data, 1-based sheet
            row = all_data[row_idx]
            line_type = row[COL_TYPE - 1] if len(row) >= COL_TYPE else ""
            scene_id  = row[COL_SCENE_ID - 1] if len(row) >= COL_SCENE_ID else ""

            # Skip non-dialog rows
            if line_type != "DIALOG":
                continue

            # Scene filter
            if selected_scenes and scene_id not in selected_scenes:
                continue

            # Skip if already has an image URL
            existing_url = row[COL_IMG_URL - 1] if len(row) >= COL_IMG_URL else ""
            if skip_existing and existing_url:
                continue

            dialog_rows.append((row_idx, row, scene_id))

        total = len(dialog_rows)
        if on_progress:
            on_progress(0, total, f"Found {total} dialog rows to process…")

        # Batch updates for performance
        batch_prompt = []
        batch_url = []

        for i, (row_idx, row, scene_id) in enumerate(dialog_rows):
            sheet_row = row_idx + 1  # convert to 1-based sheet row

            character = row[COL_CHARACTER - 1] if len(row) >= COL_CHARACTER else ""
            text      = row[COL_TEXT - 1] if len(row) >= COL_TEXT else ""
            emotion   = row[COL_EMOTION - 1] if len(row) >= COL_EMOTION else ""

            scene = scene_map.get(scene_id)
            if not scene:
                continue

            label = f"{character}: {text[:40]}…" if len(text) > 40 else f"{character}: {text}"
            if on_progress:
                on_progress(i, total, f"[{i+1}/{total}] Prompting — {label}")

            # Find the line index within the scene for per-line prompt
            line_index = self._find_line_index(scene, character, text)

            if line_index is not None:
                prompt = prompt_gen.generate_per_line(
                    scene, char_sheet, loc_sheet, line_index, extra_style
                )
            else:
                prompt = prompt_gen.generate(scene, char_sheet, loc_sheet, extra_style)

            image_url = self.build_image_url(prompt)

            # Queue cell updates
            batch_prompt.append({"range": f"M{sheet_row}", "values": [[prompt]]})
            batch_url.append({
                "range": f"O{sheet_row}",
                "values": [[f'=IMAGE("{image_url}")']],
            })
            updated += 1

            # Flush in batches of 10 to avoid hitting API rate limits
            if len(batch_prompt) >= 10:
                self._flush_batch(ws, batch_prompt, batch_url)
                batch_prompt.clear()
                batch_url.clear()

        # Final flush
        if batch_prompt:
            self._flush_batch(ws, batch_prompt, batch_url)

        if on_progress:
            on_progress(total, total, f"Done — {updated} images pushed to sheet")

        # Set row height for image visibility
        self._set_image_row_heights(ws, [r[0] + 1 for r in dialog_rows])

        return updated

    # ------------------------------------------------------------------
    # Run without Google Sheets  —  local-only / CSV mode
    # ------------------------------------------------------------------

    def generate_prompts_and_urls(
        self,
        script: Script,
        char_sheet: CharacterSheet,
        loc_sheet: LocationSheet,
        selected_scenes: Optional[list[str]] = None,
        extra_style: str = "",
        on_progress=None,
    ) -> list[dict]:
        """
        Generate prompts + Pollinations URLs for every dialog line.
        Returns a list of dicts (scene_id, character, text, prompt, image_url).
        Does NOT require Google Sheets auth.
        """
        from generators.prompt_generator import PromptGenerator
        prompt_gen = PromptGenerator(api_key=self._api_key)

        results = []
        scenes = [s for s in script.scenes if not selected_scenes or s.id in selected_scenes]

        dialog_lines = []
        for scene in scenes:
            for li, line in enumerate(scene.lines):
                if line.type == "dialog":
                    dialog_lines.append((scene, li, line))

        total = len(dialog_lines)
        for i, (scene, li, line) in enumerate(dialog_lines):
            if on_progress:
                on_progress(i, total, f"[{i+1}/{total}] {line.character}: {line.text[:40]}…")

            prompt = prompt_gen.generate_per_line(
                scene, char_sheet, loc_sheet, li, extra_style
            )
            url = self.build_image_url(prompt)

            results.append({
                "scene_id": scene.id,
                "character": line.character or "",
                "text": line.text,
                "emotion": line.emotion or "",
                "prompt": prompt,
                "image_url": url,
            })

        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_line_index(self, scene: Scene, character: str, text: str) -> Optional[int]:
        """Find the index of a dialog line within a Scene by matching character + text."""
        for i, line in enumerate(scene.lines):
            if (line.type == "dialog"
                and line.character and line.character.lower() == character.lower()
                and line.text.strip() == text.strip()):
                return i
        # Fuzzy fallback — match by character + first 30 chars
        for i, line in enumerate(scene.lines):
            if (line.type == "dialog"
                and line.character and line.character.lower() == character.lower()
                and line.text[:30].strip() == text[:30].strip()):
                return i
        return None

    def _flush_batch(self, ws, batch_prompt, batch_url):
        """Write queued cell updates to the sheet."""
        ws.batch_update(batch_prompt, value_input_option="RAW")
        ws.batch_update(batch_url, value_input_option="USER_ENTERED")

    def _set_image_row_heights(self, ws, sheet_rows: list[int]):
        """Set row height to 120px for rows that contain images."""
        try:
            requests = []
            for row in sheet_rows:
                requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": ws.id,
                            "dimension": "ROWS",
                            "startIndex": row - 1,
                            "endIndex": row,
                        },
                        "properties": {"pixelSize": 120},
                        "fields": "pixelSize",
                    }
                })
            if requests:
                ws.spreadsheet.batch_update({"requests": requests})
        except Exception:
            pass  # row height is cosmetic — silently skip on error

    def _auth(self, service_account_json, oauth_credentials):
        """Re-use the same auth logic as SheetsExporter."""
        import gspread
        sa_path = service_account_json or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if sa_path and Path(sa_path).exists():
            return gspread.service_account(filename=sa_path)

        sa_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT")
        if sa_json_str:
            import json, tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                f.write(sa_json_str)
                return gspread.service_account(filename=f.name)

        oauth_path = oauth_credentials or os.environ.get("GOOGLE_OAUTH_CREDENTIALS")
        if oauth_path and Path(oauth_path).exists():
            return gspread.oauth(credentials_filename=oauth_path)

        raise ValueError("No Google credentials found.")
