"""Central configuration loaded from .env file."""

import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
REPLICATE_API_TOKEN: str = os.environ.get("REPLICATE_API_TOKEN", "")
STABILITY_API_KEY: str = os.environ.get("STABILITY_API_KEY", "")
IMAGE_BACKEND: str = os.environ.get("IMAGE_BACKEND", "mock")
OUTPUT_DIR: str = os.environ.get("OUTPUT_DIR", "output")

# Negative prompt applied globally to all image generations
GLOBAL_NEGATIVE_PROMPT = (
    "blurry, low quality, watermark, text overlay, ugly, deformed, "
    "bad anatomy, extra limbs, duplicate, cropped, out of frame"
)

# SDXL model on Replicate (can be overridden via env)
REPLICATE_MODEL = os.environ.get(
    "REPLICATE_MODEL",
    "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
)
