"""
Image generator — supports multiple backends:
  - replicate  : Stable Diffusion XL via Replicate API
  - stability  : Stability AI (stable-diffusion-xl-1024-v1-0)
  - mock       : Saves a placeholder PNG (no API key required, for testing)
"""

import os
import time
import uuid
import requests
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
import io


class ImageGenerator:
    BACKENDS = ("replicate", "stability", "mock")

    def __init__(
        self,
        backend: Optional[str] = None,
        output_dir: str = "output",
        replicate_token: Optional[str] = None,
        stability_key: Optional[str] = None,
    ):
        self.backend = backend or os.environ.get("IMAGE_BACKEND", "mock")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._replicate_token = replicate_token or os.environ.get("REPLICATE_API_TOKEN", "")
        self._stability_key = stability_key or os.environ.get("STABILITY_API_KEY", "")

        if self.backend not in self.BACKENDS:
            raise ValueError(f"Unknown backend '{self.backend}'. Choose from {self.BACKENDS}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        scene_id: str = "",
        negative_prompt: str = "blurry, low quality, watermark, text, ugly, deformed",
        width: int = 1024,
        height: int = 576,  # 16:9
    ) -> Path:
        """Generate an image and return the saved file path."""
        filename = f"{scene_id}_{uuid.uuid4().hex[:8]}.png" if scene_id else f"{uuid.uuid4().hex}.png"
        out_path = self.output_dir / filename

        if self.backend == "replicate":
            return self._generate_replicate(prompt, negative_prompt, width, height, out_path)
        elif self.backend == "stability":
            return self._generate_stability(prompt, negative_prompt, width, height, out_path)
        else:
            return self._generate_mock(prompt, out_path)

    # ------------------------------------------------------------------
    # Replicate backend  (SDXL via Replicate)
    # ------------------------------------------------------------------

    def _generate_replicate(
        self, prompt, negative_prompt, width, height, out_path: Path
    ) -> Path:
        import replicate

        os.environ["REPLICATE_API_TOKEN"] = self._replicate_token

        output = replicate.run(
            "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
            input={
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "num_inference_steps": 30,
                "guidance_scale": 7.5,
            },
        )
        # output is a list of URLs
        img_url = output[0] if isinstance(output, list) else output
        response = requests.get(img_url, timeout=60)
        response.raise_for_status()
        out_path.write_bytes(response.content)
        return out_path

    # ------------------------------------------------------------------
    # Stability AI backend
    # ------------------------------------------------------------------

    def _generate_stability(
        self, prompt, negative_prompt, width, height, out_path: Path
    ) -> Path:
        url = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
        headers = {
            "Authorization": f"Bearer {self._stability_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = {
            "text_prompts": [
                {"text": prompt, "weight": 1.0},
                {"text": negative_prompt, "weight": -1.0},
            ],
            "cfg_scale": 7,
            "width": width,
            "height": height,
            "samples": 1,
            "steps": 30,
        }
        response = requests.post(url, headers=headers, json=body, timeout=120)
        response.raise_for_status()
        data = response.json()
        img_b64 = data["artifacts"][0]["base64"]
        import base64
        out_path.write_bytes(base64.b64decode(img_b64))
        return out_path

    # ------------------------------------------------------------------
    # Mock backend — generates a labeled placeholder image
    # ------------------------------------------------------------------

    def _generate_mock(self, prompt: str, out_path: Path) -> Path:
        width, height = 1024, 576
        img = Image.new("RGB", (width, height), color=(30, 30, 50))
        draw = ImageDraw.Draw(img)

        # Border
        draw.rectangle([10, 10, width - 10, height - 10], outline=(100, 150, 200), width=3)

        # Title
        draw.text((width // 2, 40), "[MOCK IMAGE]", fill=(200, 200, 255), anchor="mm")

        # Wrap and draw prompt text
        words = prompt.split()
        lines, current = [], []
        for word in words:
            current.append(word)
            if len(" ".join(current)) > 80:
                lines.append(" ".join(current[:-1]))
                current = [word]
        if current:
            lines.append(" ".join(current))

        y = 100
        for line in lines[:12]:
            draw.text((width // 2, y), line, fill=(180, 220, 180), anchor="mm")
            y += 30

        img.save(out_path, "PNG")
        return out_path
