"""
Video Generator
===============
Converts a still image into a short animated video clip.

Backend: Replicate — stability-ai/stable-video-diffusion (SVD)
Free tier: Replicate gives $5 credit on signup, SVD costs ~$0.01/run.

Pipeline step 4:  Image URL  →  Video URL (.mp4)

Usage
─────
    from generators.video_generator import VideoGenerator

    vg = VideoGenerator(replicate_token="r8_...")
    video_url = vg.generate(image_url="https://image.pollinations.ai/prompt/...")
    print(video_url)  # https://replicate.delivery/...
"""

import os
import time
from typing import Optional


# Replicate model — Stable Video Diffusion XT (25 frames, 6fps)
SVD_MODEL = (
    "stability-ai/stable-video-diffusion:"
    "3f0457e4619daac51203dedb472816fd4af51f3af89d874b8e0aa5cd2a0e421"
)

# Cheaper/faster alternative on Replicate (AnimateDiff img2vid)
ANIMATEDIFF_MODEL = (
    "lucataco/animate-diff:"
    "beecf59c4ea3f37da2d4e11d4cfd1803ce8d9ddc37e2c93c4b01f7a1ebf89f6"
)


class VideoGenerator:
    """
    Step 4 of the pipeline: Image URL → short .mp4 video URL.

    Uses Replicate's Stable Video Diffusion model by default.
    Falls back to a mock (returns image URL unchanged) if no token is set.
    """

    BACKENDS = ("replicate", "mock")

    def __init__(
        self,
        replicate_token: Optional[str] = None,
        backend: Optional[str] = None,
        fps: int = 8,
        motion_bucket_id: int = 127,   # 1-255: higher = more motion
        cond_aug: float = 0.02,
        decode_chunk_size: int = 8,
    ):
        self._token = replicate_token or os.environ.get("REPLICATE_API_TOKEN", "")
        self.backend = backend or ("replicate" if self._token else "mock")
        self.fps = fps
        self.motion_bucket_id = motion_bucket_id
        self.cond_aug = cond_aug
        self.decode_chunk_size = decode_chunk_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, image_url: str) -> str:
        """
        Animate the given image URL and return a video URL (.mp4).
        In mock mode returns the original image URL unchanged.
        """
        if self.backend == "mock":
            return image_url  # pass-through for testing without credits

        return self._generate_replicate(image_url)

    # ------------------------------------------------------------------
    # Replicate SVD backend
    # ------------------------------------------------------------------

    def _generate_replicate(self, image_url: str) -> str:
        import replicate

        os.environ["REPLICATE_API_TOKEN"] = self._token

        output = replicate.run(
            SVD_MODEL,
            input={
                "input_image": image_url,
                "frames_per_second": self.fps,
                "motion_bucket_id": self.motion_bucket_id,
                "cond_aug": self.cond_aug,
                "decode_chunk_size": self.decode_chunk_size,
                "sizing_strategy": "maintain_aspect_ratio",
            },
        )

        # output is a FileOutput object or URL string
        if hasattr(output, "url"):
            return output.url
        return str(output)
