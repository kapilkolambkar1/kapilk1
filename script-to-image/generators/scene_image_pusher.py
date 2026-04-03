"""
Scene Image Pusher
==================
After a Google Sheet has been created (Tab 1 = Script, Tab 2 = Character Canvas),
this module drives the 4-step pipeline per dialog row:

  Col J  Dialog text      (already in sheet)
  Col M  Image Prompt     ← Step 2: Claude generates from dialog + context
  Col O  Image URL        ← Step 3: Pollinations.ai =IMAGE() formula
  Col P  Video URL        ← Step 4: Replicate SVD =IMAGE() / video link

Each step can be run independently — skip any step you don't need.

Usage
─────
    from generators.scene_image_pusher import SceneImagePusher

    pusher = SceneImagePusher(anthropic_api_key="sk-ant-...",
                              replicate_token="r8_...")

    # Step 2+3+4 all at once
    pusher.run(spreadsheet_url="https://docs.google.com/...", ...)

    # Steps individually
    pusher.push_prompts(spreadsheet_url, ...)   # writes col M
    pusher.push_images(spreadsheet_url, ...)    # reads col M → writes col O
    pusher.push_videos(spreadsheet_url, ...)    # reads col O → writes col P
"""

import os
import urllib.parse
from pathlib import Path
from typing import Optional

from models.character import CharacterSheet
from models.location import LocationSheet
from models.script import Script, Scene


# ── Column indices (1-based) in the "Script" worksheet ──────────────────────
COL_SCENE_ID   = 2
COL_TYPE       = 8   # H
COL_CHARACTER  = 9   # I
COL_TEXT       = 10  # J  ← dialog source
COL_EMOTION    = 11  # K
COL_IMG_PROMPT = 13  # M  ← step 2: generated prompt
COL_IMG_URL    = 15  # O  ← step 3: image =IMAGE(url)
COL_VIDEO_URL  = 16  # P  ← step 4: video url / =IMAGE(url)

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"


class SceneImagePusher:
    """
    Drives the 4-step dialog → prompt → image → video pipeline,
    writing results back into the Google Sheet per dialog row.
    """

    def __init__(
        self,
        anthropic_api_key: Optional[str] = None,
        replicate_token: Optional[str] = None,
        pollinations_model: str = "flux",
        image_width: int = 1024,
        image_height: int = 576,
        seed: Optional[int] = 42,
        video_fps: int = 8,
        video_motion: int = 100,
    ):
        self._api_key       = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._rep_token     = replicate_token or os.environ.get("REPLICATE_API_TOKEN", "")
        self.poll_model     = pollinations_model
        self.width          = image_width
        self.height         = image_height
        self.seed           = seed
        self.video_fps      = video_fps
        self.video_motion   = video_motion

    # ── Convenience: run all steps ──────────────────────────────────────────

    def run(
        self,
        spreadsheet_url: str,
        script: Script,
        char_sheet: CharacterSheet,
        loc_sheet: LocationSheet,
        service_account_json: Optional[str] = None,
        oauth_credentials: Optional[str] = None,
        skip_existing: bool = True,
        selected_scenes: Optional[list[str]] = None,
        extra_style: str = "",
        include_video: bool = False,
        on_progress=None,
    ) -> dict:
        """
        Run step 2 (prompts) + step 3 (images) and optionally step 4 (video).
        Returns {"prompts": N, "images": N, "videos": N}.
        """
        ws = self._open_ws(spreadsheet_url, service_account_json, oauth_credentials)
        self._ensure_headers(ws)

        scene_map = {s.id: s for s in script.scenes}
        rows = self._collect_dialog_rows(ws, selected_scenes, skip_existing,
                                         check_col=COL_IMG_URL)

        total = len(rows)
        if on_progress:
            on_progress(0, total, f"Found {total} dialog rows…")

        from generators.prompt_generator import PromptGenerator
        prompt_gen = PromptGenerator(api_key=self._api_key)

        batch_m, batch_o, batch_p = [], [], []
        p_count = i_count = v_count = 0

        for i, (row_idx, row, scene_id) in enumerate(rows):
            sheet_row = row_idx + 1
            character = _cell(row, COL_CHARACTER)
            text      = _cell(row, COL_TEXT)
            emotion   = _cell(row, COL_EMOTION)
            scene     = scene_map.get(scene_id)
            if not scene:
                continue

            label = f"{character}: {text[:45]}…" if len(text) > 45 else f"{character}: {text}"

            # ── Step 2: generate prompt ──────────────────────────────────
            if on_progress:
                on_progress(i, total, f"[{i+1}/{total}] Prompt — {label}")

            line_idx = self._find_line_index(scene, character, text)
            if line_idx is not None:
                prompt = prompt_gen.generate_per_line(
                    scene, char_sheet, loc_sheet, line_idx, extra_style)
            else:
                prompt = prompt_gen.generate(scene, char_sheet, loc_sheet, extra_style)

            batch_m.append({"range": f"M{sheet_row}", "values": [[prompt]]})
            p_count += 1

            # ── Step 3: image URL ────────────────────────────────────────
            image_url = self.build_image_url(prompt)
            batch_o.append({
                "range": f"O{sheet_row}",
                "values": [[f'=IMAGE("{image_url}")']],
            })
            i_count += 1

            # ── Step 4: video (optional) ─────────────────────────────────
            if include_video and self._rep_token:
                if on_progress:
                    on_progress(i, total, f"[{i+1}/{total}] Video — {label}")
                try:
                    from generators.video_generator import VideoGenerator
                    vg = VideoGenerator(replicate_token=self._rep_token,
                                        fps=self.video_fps,
                                        motion_bucket_id=self.video_motion)
                    video_url = vg.generate(image_url)
                    batch_p.append({"range": f"P{sheet_row}", "values": [[video_url]]})
                    v_count += 1
                except Exception:
                    pass  # video failures are non-fatal

            # Flush every 10 rows
            if len(batch_m) >= 10:
                self._flush(ws, batch_m, batch_o, batch_p)
                batch_m.clear(); batch_o.clear(); batch_p.clear()

        self._flush(ws, batch_m, batch_o, batch_p)
        self._set_row_heights(ws, [r[0] + 1 for r in rows])

        if on_progress:
            on_progress(total, total, f"Done — {i_count} images pushed")

        return {"prompts": p_count, "images": i_count, "videos": v_count}

    # ── Step 2 only: push prompts to col M ──────────────────────────────────

    def push_prompts(
        self,
        spreadsheet_url: str,
        script: Script,
        char_sheet: CharacterSheet,
        loc_sheet: LocationSheet,
        service_account_json: Optional[str] = None,
        oauth_credentials: Optional[str] = None,
        skip_existing: bool = True,
        selected_scenes: Optional[list[str]] = None,
        extra_style: str = "",
        on_progress=None,
    ) -> int:
        """Generate prompts from dialog (col J) and write to col M. Returns count."""
        from generators.prompt_generator import PromptGenerator
        prompt_gen = PromptGenerator(api_key=self._api_key)

        ws = self._open_ws(spreadsheet_url, service_account_json, oauth_credentials)
        self._ensure_headers(ws)
        scene_map = {s.id: s for s in script.scenes}
        rows = self._collect_dialog_rows(ws, selected_scenes, skip_existing,
                                         check_col=COL_IMG_PROMPT)

        total = len(rows)
        batch = []
        count = 0
        for i, (row_idx, row, scene_id) in enumerate(rows):
            sheet_row = row_idx + 1
            character = _cell(row, COL_CHARACTER)
            text      = _cell(row, COL_TEXT)
            scene     = scene_map.get(scene_id)
            if not scene:
                continue
            if on_progress:
                on_progress(i, total, f"[{i+1}/{total}] {character}: {text[:40]}")

            line_idx = self._find_line_index(scene, character, text)
            prompt = (
                prompt_gen.generate_per_line(scene, char_sheet, loc_sheet, line_idx, extra_style)
                if line_idx is not None
                else prompt_gen.generate(scene, char_sheet, loc_sheet, extra_style)
            )
            batch.append({"range": f"M{sheet_row}", "values": [[prompt]]})
            count += 1
            if len(batch) >= 10:
                ws.batch_update(batch, value_input_option="RAW")
                batch.clear()
        if batch:
            ws.batch_update(batch, value_input_option="RAW")
        return count

    # ── Step 3 only: read col M prompts → generate images → write col O ─────

    def push_images(
        self,
        spreadsheet_url: str,
        service_account_json: Optional[str] = None,
        oauth_credentials: Optional[str] = None,
        skip_existing: bool = True,
        selected_scenes: Optional[list[str]] = None,
        on_progress=None,
    ) -> int:
        """
        Read prompts from col M, generate Pollinations images, write =IMAGE() to col O.
        Works even without a Script/CharacterSheet — prompts are already in the sheet.
        """
        ws = self._open_ws(spreadsheet_url, service_account_json, oauth_credentials)
        self._ensure_headers(ws)
        all_data = ws.get_all_values()

        batch = []
        img_rows = []
        count = 0

        rows_to_process = []
        for row_idx in range(1, len(all_data)):
            row = all_data[row_idx]
            if _cell(row, COL_TYPE) != "DIALOG":
                continue
            scene_id = _cell(row, COL_SCENE_ID)
            if selected_scenes and scene_id not in selected_scenes:
                continue
            existing = _cell(row, COL_IMG_URL)
            if skip_existing and existing:
                continue
            prompt = _cell(row, COL_IMG_PROMPT)
            if not prompt:
                continue
            rows_to_process.append((row_idx, prompt))

        total = len(rows_to_process)
        for i, (row_idx, prompt) in enumerate(rows_to_process):
            sheet_row = row_idx + 1
            if on_progress:
                on_progress(i, total, f"[{i+1}/{total}] Generating image…")
            img_url = self.build_image_url(prompt)
            batch.append({"range": f"O{sheet_row}", "values": [[f'=IMAGE("{img_url}")']]})
            img_rows.append(sheet_row)
            count += 1
            if len(batch) >= 10:
                ws.batch_update(batch, value_input_option="USER_ENTERED")
                batch.clear()
        if batch:
            ws.batch_update(batch, value_input_option="USER_ENTERED")

        self._set_row_heights(ws, img_rows)
        return count

    # ── Step 4 only: read col O image URLs → generate videos → write col P ──

    def push_videos(
        self,
        spreadsheet_url: str,
        service_account_json: Optional[str] = None,
        oauth_credentials: Optional[str] = None,
        skip_existing: bool = True,
        selected_scenes: Optional[list[str]] = None,
        on_progress=None,
    ) -> int:
        """
        Read image URLs from col O, generate SVD videos via Replicate, write to col P.
        """
        from generators.video_generator import VideoGenerator
        vg = VideoGenerator(replicate_token=self._rep_token,
                            fps=self.video_fps,
                            motion_bucket_id=self.video_motion)

        ws = self._open_ws(spreadsheet_url, service_account_json, oauth_credentials)
        self._ensure_headers(ws)
        all_data = ws.get_all_values()

        count = 0
        batch = []

        rows_to_process = []
        for row_idx in range(1, len(all_data)):
            row = all_data[row_idx]
            if _cell(row, COL_TYPE) != "DIALOG":
                continue
            scene_id = _cell(row, COL_SCENE_ID)
            if selected_scenes and scene_id not in selected_scenes:
                continue
            if skip_existing and _cell(row, COL_VIDEO_URL):
                continue
            # Extract raw URL from =IMAGE("url") formula if needed
            img_cell = _cell(row, COL_IMG_URL)
            img_url = _extract_url(img_cell)
            if not img_url:
                continue
            rows_to_process.append((row_idx, img_url))

        total = len(rows_to_process)
        for i, (row_idx, img_url) in enumerate(rows_to_process):
            sheet_row = row_idx + 1
            if on_progress:
                on_progress(i, total, f"[{i+1}/{total}] Generating video…")
            try:
                video_url = vg.generate(img_url)
                batch.append({"range": f"P{sheet_row}", "values": [[video_url]]})
                count += 1
            except Exception:
                pass  # non-fatal
            if len(batch) >= 5:
                ws.batch_update(batch, value_input_option="USER_ENTERED")
                batch.clear()
        if batch:
            ws.batch_update(batch, value_input_option="USER_ENTERED")
        return count

    # ── Local preview (no Google Sheets) ────────────────────────────────────

    def generate_prompts_and_urls(
        self,
        script: Script,
        char_sheet: CharacterSheet,
        loc_sheet: LocationSheet,
        selected_scenes: Optional[list[str]] = None,
        extra_style: str = "",
        include_video: bool = False,
        on_progress=None,
    ) -> list[dict]:
        """
        Run the full pipeline locally without touching a Google Sheet.
        Returns list of dicts: {scene_id, character, text, prompt, image_url, video_url}.
        """
        from generators.prompt_generator import PromptGenerator
        prompt_gen = PromptGenerator(api_key=self._api_key)

        results = []
        scenes = [s for s in script.scenes
                  if not selected_scenes or s.id in selected_scenes]
        dialog_lines = [
            (scene, li, line)
            for scene in scenes
            for li, line in enumerate(scene.lines)
            if line.type == "dialog"
        ]

        total = len(dialog_lines)
        for i, (scene, li, line) in enumerate(dialog_lines):
            if on_progress:
                on_progress(i, total,
                            f"[{i+1}/{total}] {line.character}: {line.text[:40]}…")

            prompt    = prompt_gen.generate_per_line(
                scene, char_sheet, loc_sheet, li, extra_style)
            image_url = self.build_image_url(prompt)
            video_url = ""

            if include_video and self._rep_token:
                try:
                    from generators.video_generator import VideoGenerator
                    vg = VideoGenerator(replicate_token=self._rep_token,
                                        fps=self.video_fps,
                                        motion_bucket_id=self.video_motion)
                    video_url = vg.generate(image_url)
                except Exception:
                    pass

            results.append({
                "scene_id":  scene.id,
                "character": line.character or "",
                "text":      line.text,
                "emotion":   line.emotion or "",
                "prompt":    prompt,
                "image_url": image_url,
                "video_url": video_url,
            })

        return results

    # ── Utilities ────────────────────────────────────────────────────────────

    def build_image_url(self, prompt: str) -> str:
        encoded = urllib.parse.quote(prompt, safe="")
        params = (f"?width={self.width}&height={self.height}"
                  f"&model={self.poll_model}&nologo=true&enhance=false")
        if self.seed is not None:
            params += f"&seed={self.seed}"
        return f"{POLLINATIONS_BASE}/{encoded}{params}"

    def _open_ws(self, url, sa_json, oauth):
        gc = self._auth(sa_json, oauth)
        return gc.open_by_url(url).worksheet("Script")

    def _ensure_headers(self, ws):
        header = ws.row_values(1)
        updates = []
        if len(header) < COL_IMG_PROMPT or header[COL_IMG_PROMPT-1] != "Image Prompt":
            updates.append({"range": f"M1", "values": [["Image Prompt"]]})
        if len(header) < COL_IMG_URL or header[COL_IMG_URL-1] != "Image URL":
            updates.append({"range": f"O1", "values": [["Image URL"]]})
        if len(header) < COL_VIDEO_URL or header[COL_VIDEO_URL-1] != "Video URL":
            updates.append({"range": f"P1", "values": [["Video URL"]]})
        if updates:
            ws.batch_update(updates, value_input_option="RAW")

    def _collect_dialog_rows(self, ws, selected_scenes, skip_existing, check_col):
        all_data = ws.get_all_values()
        rows = []
        for row_idx in range(1, len(all_data)):
            row = all_data[row_idx]
            if _cell(row, COL_TYPE) != "DIALOG":
                continue
            scene_id = _cell(row, COL_SCENE_ID)
            if selected_scenes and scene_id not in selected_scenes:
                continue
            if skip_existing and _cell(row, check_col):
                continue
            rows.append((row_idx, row, scene_id))
        return rows

    def _flush(self, ws, batch_m, batch_o, batch_p):
        if batch_m:
            ws.batch_update(batch_m, value_input_option="RAW")
        if batch_o:
            ws.batch_update(batch_o, value_input_option="USER_ENTERED")
        if batch_p:
            ws.batch_update(batch_p, value_input_option="USER_ENTERED")

    def _set_row_heights(self, ws, sheet_rows: list[int]):
        try:
            reqs = [{
                "updateDimensionProperties": {
                    "range": {"sheetId": ws.id, "dimension": "ROWS",
                              "startIndex": r - 1, "endIndex": r},
                    "properties": {"pixelSize": 130},
                    "fields": "pixelSize",
                }
            } for r in sheet_rows]
            if reqs:
                ws.spreadsheet.batch_update({"requests": reqs})
        except Exception:
            pass

    def _find_line_index(self, scene, character, text):
        for i, line in enumerate(scene.lines):
            if (line.type == "dialog"
                    and line.character
                    and line.character.lower() == character.lower()
                    and line.text.strip() == text.strip()):
                return i
        for i, line in enumerate(scene.lines):
            if (line.type == "dialog"
                    and line.character
                    and line.character.lower() == character.lower()
                    and line.text[:30].strip() == text[:30].strip()):
                return i
        return None

    def _auth(self, service_account_json, oauth_credentials):
        import gspread
        sa_path = service_account_json or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if sa_path and Path(sa_path).exists():
            return gspread.service_account(filename=sa_path)
        sa_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT")
        if sa_str:
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                f.write(sa_str)
                return gspread.service_account(filename=f.name)
        oauth_path = oauth_credentials or os.environ.get("GOOGLE_OAUTH_CREDENTIALS")
        if oauth_path and Path(oauth_path).exists():
            return gspread.oauth(credentials_filename=oauth_path)
        raise ValueError("No Google credentials found.")


# ── Module helpers ────────────────────────────────────────────────────────────

def _cell(row: list, col: int) -> str:
    """Safe 1-based column access."""
    return row[col - 1].strip() if len(row) >= col else ""


def _extract_url(cell_value: str) -> str:
    """Extract raw URL from =IMAGE("url") formula or return as-is if already a URL."""
    v = cell_value.strip()
    if v.startswith('=IMAGE("') and v.endswith('")'):
        return v[8:-2]
    if v.startswith("http"):
        return v
    return ""
