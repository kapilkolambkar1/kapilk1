"""
Image Sheet Generator
=====================
Builds a full storyboard contact sheet from a Script:
  1. Generates an image prompt per scene (via Claude)
  2. Fetches images from Pollinations.ai  — completely free, no API key needed
     https://pollinations.ai
  3. Composites all frames into a labelled grid sheet (Pillow)

Pollinations.ai endpoint:
  GET https://image.pollinations.ai/prompt/{url-encoded-prompt}
      ?width=W&height=H&seed=S&model=flux&nologo=true

Usage:
    from generators.image_sheet import ImageSheetGenerator
    gen = ImageSheetGenerator()
    sheet_path = gen.build(script, char_sheet, loc_sheet, output_dir="output")
"""

import io
import math
import os
import textwrap
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, ImageDraw, ImageFont

from models.character import CharacterSheet
from models.location import LocationSheet
from models.script import Scene, Script


# ---------------------------------------------------------------------------
# Frame — one cell in the sheet
# ---------------------------------------------------------------------------

@dataclass
class SheetFrame:
    scene_id: str
    prompt: str
    image: Optional[Image.Image] = None
    character_names: list[str] = field(default_factory=list)
    dialog_snippet: str = ""
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class ImageSheetGenerator:
    """
    Generates a storyboard image sheet from a Script using:
      - Claude  : builds image prompts from scene context
      - Pollinations.ai : renders each prompt (free, no API key)
      - Pillow  : composites frames into a printable sheet
    """

    POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"

    # Layout constants (pixels)
    FRAME_W = 512
    FRAME_H = 288          # 16:9
    LABEL_H = 72           # height of the text label below each frame
    CELL_H  = FRAME_H + LABEL_H
    PADDING = 16
    COLS    = 3            # frames per row

    # Sheet header
    HEADER_H = 60
    BG_COLOR      = (18, 18, 28)
    BORDER_COLOR  = (60, 80, 120)
    LABEL_BG      = (28, 28, 42)
    TEXT_COLOR    = (200, 210, 230)
    ACCENT_COLOR  = (100, 160, 255)
    ERROR_COLOR   = (220, 80, 80)

    def __init__(self, anthropic_api_key: Optional[str] = None, cols: int = 3):
        self.COLS = cols
        self._anthropic_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        script: Script,
        characters: CharacterSheet,
        locations: LocationSheet,
        output_dir: str = "output",
        extra_style: str = "",
        per_line: bool = False,
        scene_filter: Optional[str] = None,
        pollinations_model: str = "flux",
        seed: Optional[int] = None,
        on_progress=None,           # optional callback(current, total, label)
    ) -> Path:
        """
        Full pipeline: prompts → images → composite sheet.

        Returns the path to the saved PNG sheet.
        """
        from generators.prompt_generator import PromptGenerator
        prompt_gen = PromptGenerator(api_key=self._anthropic_key)

        scenes = [
            s for s in script.scenes
            if not scene_filter or s.id == scene_filter
        ]

        # ---- Step 1: generate prompts & build frame list ----------------
        frames: list[SheetFrame] = []
        total = len(scenes)

        for idx, scene in enumerate(scenes):
            if on_progress:
                on_progress(idx, total, f"Prompting {scene.id}…")

            if per_line:
                dialog_indices = [
                    i for i, l in enumerate(scene.lines)
                    if l.type == "dialog" or l.generate_image
                ]
                for li in dialog_indices:
                    line = scene.lines[li]
                    prompt = prompt_gen.generate_per_line(
                        scene, characters, locations, li, extra_style
                    )
                    frames.append(SheetFrame(
                        scene_id=f"{scene.id}·L{li}",
                        prompt=prompt,
                        character_names=[line.character] if line.character else [],
                        dialog_snippet=line.text[:80],
                    ))
            else:
                prompt = prompt_gen.generate(scene, characters, locations, extra_style)
                snippet = next(
                    (l.text for l in scene.lines if l.type == "dialog"), ""
                )
                frames.append(SheetFrame(
                    scene_id=scene.id,
                    prompt=prompt,
                    character_names=list(scene.characters),
                    dialog_snippet=snippet[:80],
                ))

        # ---- Step 2: fetch images from Pollinations.ai ------------------
        for idx, frame in enumerate(frames):
            if on_progress:
                on_progress(idx, len(frames), f"Fetching image: {frame.scene_id}…")
            frame.image = self._fetch_pollinations(
                frame.prompt,
                width=self.FRAME_W,
                height=self.FRAME_H,
                model=pollinations_model,
                seed=seed,
            )

        # ---- Step 3: composite into a sheet -----------------------------
        sheet = self._composite(frames, title=script.title)

        # ---- Step 4: save -----------------------------------------------
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"sheet_{script.title.replace(' ', '_')}_{uuid.uuid4().hex[:6]}.png"
        out_path = out_dir / filename
        sheet.save(out_path, "PNG")
        return out_path

    # ------------------------------------------------------------------
    # Pollinations.ai fetch
    # ------------------------------------------------------------------

    def _fetch_pollinations(
        self,
        prompt: str,
        width: int = 512,
        height: int = 288,
        model: str = "flux",
        seed: Optional[int] = None,
        retries: int = 3,
    ) -> Optional[Image.Image]:
        """
        Call Pollinations.ai to generate an image for the given prompt.
        Returns a PIL Image, or None on failure.

        Docs: https://pollinations.ai
        Free tier: unlimited, no sign-up required.
        """
        encoded = urllib.parse.quote(prompt, safe="")
        url = self.POLLINATIONS_URL.format(prompt=encoded)
        params = {
            "width": width,
            "height": height,
            "model": model,
            "nologo": "true",
            "enhance": "false",
        }
        if seed is not None:
            params["seed"] = seed

        for attempt in range(retries):
            try:
                resp = requests.get(url, params=params, timeout=90)
                resp.raise_for_status()
                return Image.open(io.BytesIO(resp.content)).convert("RGB")
            except Exception as exc:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    # Return an error placeholder image
                    return self._error_image(str(exc))
        return None

    # ------------------------------------------------------------------
    # Compositing
    # ------------------------------------------------------------------

    def _composite(self, frames: list[SheetFrame], title: str = "") -> Image.Image:
        """Arrange frames into a labelled grid sheet."""
        cols = self.COLS
        rows = math.ceil(len(frames) / cols)

        sheet_w = cols * (self.FRAME_W + self.PADDING) + self.PADDING
        sheet_h = (self.HEADER_H + self.PADDING
                   + rows * (self.CELL_H + self.PADDING)
                   + self.PADDING)

        sheet = Image.new("RGB", (sheet_w, sheet_h), self.BG_COLOR)
        draw = ImageDraw.Draw(sheet)

        # Title header
        self._draw_header(draw, sheet_w, title)

        for i, frame in enumerate(frames):
            row, col = divmod(i, cols)
            x = self.PADDING + col * (self.FRAME_W + self.PADDING)
            y = self.HEADER_H + self.PADDING + row * (self.CELL_H + self.PADDING)

            # Frame image
            if frame.image:
                img = frame.image.resize((self.FRAME_W, self.FRAME_H), Image.LANCZOS)
            else:
                img = self._error_image("No image")

            sheet.paste(img, (x, y))

            # Border around frame
            draw.rectangle(
                [x - 1, y - 1, x + self.FRAME_W, y + self.FRAME_H],
                outline=self.BORDER_COLOR, width=1
            )

            # Label strip below frame
            self._draw_label(draw, x, y + self.FRAME_H, frame)

        return sheet

    def _draw_header(self, draw: ImageDraw.ImageDraw, width: int, title: str) -> None:
        draw.rectangle([0, 0, width, self.HEADER_H], fill=(12, 12, 22))
        draw.text(
            (width // 2, self.HEADER_H // 2),
            f"Storyboard — {title}" if title else "Storyboard",
            fill=self.ACCENT_COLOR,
            anchor="mm",
        )
        draw.line([(0, self.HEADER_H), (width, self.HEADER_H)], fill=self.BORDER_COLOR, width=1)

    def _draw_label(
        self, draw: ImageDraw.ImageDraw, x: int, y: int, frame: SheetFrame
    ) -> None:
        draw.rectangle(
            [x, y, x + self.FRAME_W, y + self.LABEL_H],
            fill=self.LABEL_BG
        )

        # Scene ID
        draw.text((x + 6, y + 6), frame.scene_id, fill=self.ACCENT_COLOR)

        # Characters
        if frame.character_names:
            chars = ", ".join(frame.character_names)
            draw.text((x + 6, y + 22), f"👤 {chars[:40]}", fill=(160, 200, 160))

        # Dialog snippet (wrapped)
        if frame.dialog_snippet:
            snippet = frame.dialog_snippet[:60]
            draw.text((x + 6, y + 38), f'"{snippet}"', fill=(160, 160, 190))

    def _error_image(self, message: str) -> Image.Image:
        img = Image.new("RGB", (self.FRAME_W, self.FRAME_H), (35, 15, 15))
        draw = ImageDraw.Draw(img)
        draw.rectangle([2, 2, self.FRAME_W - 3, self.FRAME_H - 3], outline=self.ERROR_COLOR, width=2)
        draw.text((self.FRAME_W // 2, self.FRAME_H // 2 - 10), "⚠ Image error", fill=self.ERROR_COLOR, anchor="mm")
        for i, chunk in enumerate(textwrap.wrap(message, 50)[:3]):
            draw.text((self.FRAME_W // 2, self.FRAME_H // 2 + 10 + i * 16), chunk, fill=(160, 100, 100), anchor="mm")
        return img
