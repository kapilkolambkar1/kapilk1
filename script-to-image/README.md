# Script-to-Image Generator

Converts screenplay scripts into AI-generated storyboard images using **character sheets**, **location definitions**, and dialog-aware prompt generation.

## How It Works

```
Script (JSON / Fountain)
        +
Character Sheet (JSON)   -->  Claude (prompt engineer)  -->  SDXL / Stability AI  -->  Images
        +
Location Sheet (JSON)
```

1. **Parse** — reads your script (JSON or `.fountain` format)
2. **Context assembly** — combines the scene's characters (physical descriptions from the sheet) + location (visual details from the sheet) + dialog lines
3. **Prompt generation** — Claude reads the scene context and writes an optimized image generation prompt
4. **Image generation** — the prompt is sent to Stable Diffusion XL (via Replicate or Stability AI)

---

## Setup

```bash
cd script-to-image
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your API keys
```

### API Keys

| Key | Where to get it |
|-----|----------------|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `REPLICATE_API_TOKEN` | replicate.com |
| `STABILITY_API_KEY` | platform.stability.ai |

Set `IMAGE_BACKEND=replicate` or `IMAGE_BACKEND=stability` in `.env`.
Use `IMAGE_BACKEND=mock` to test without any image API key (generates placeholder PNGs).

---

## Usage

### Generate images for all scenes
```bash
python main.py generate \
  --script examples/sample_script.json \
  --characters examples/characters.json \
  --locations examples/locations.json \
  --backend mock
```

### One image per dialog line (detailed storyboard)
```bash
python main.py generate \
  --script examples/sample_script.json \
  --characters examples/characters.json \
  --locations examples/locations.json \
  --backend replicate \
  --per-line
```

### Use a Fountain screenplay
```bash
python main.py generate \
  --script examples/sample_script.fountain \
  --characters examples/characters.json \
  --locations examples/locations.json \
  --backend mock
```

### Only process one scene
```bash
python main.py generate ... --scene scene_02
```

### Dry run (show prompts, skip image generation)
```bash
python main.py generate ... --dry-run
```

### Inspect loaded sheets
```bash
python main.py inspect \
  --characters examples/characters.json \
  --locations examples/locations.json
```

---

## File Formats

### Character Sheet (`characters.json`)
```json
[
  {
    "name": "Elena",
    "age": "late 20s",
    "gender": "woman",
    "hair": "long dark brown wavy",
    "eyes": "almond-shaped green",
    "clothing_style": "worn leather jacket, dark jeans",
    "distinguishing_features": ["small scar above left eyebrow"],
    "art_style_tags": ["cinematic portrait"]
  }
]
```

### Location Sheet (`locations.json`)
```json
[
  {
    "name": "neon alley",
    "description": "narrow rain-slicked urban alley, neon signs reflecting off wet cobblestones",
    "time_of_day": "midnight",
    "weather": "light rain, mist",
    "mood": "noir, tense",
    "art_style_tags": ["cyberpunk", "blade runner aesthetic"]
  }
]
```

### Script (`script.json`)
```json
{
  "title": "My Script",
  "scenes": [
    {
      "id": "scene_01",
      "location": "neon alley",
      "time_of_day": "midnight",
      "characters": ["Elena", "Marcus"],
      "lines": [
        { "type": "action", "text": "Elena sprints into the alley." },
        { "type": "dialog", "character": "Marcus", "text": "Stop right there.", "emotion": "threatening" }
      ]
    }
  ]
}
```

Set `"generate_image": true` on any line to force a per-line image even without `--per-line`.

---

## Image Backends

| Backend | Model | Notes |
|---------|-------|-------|
| `replicate` | Stable Diffusion XL (SDXL) | Best quality, needs Replicate token |
| `stability` | stable-diffusion-xl-1024-v1-0 | Stability AI direct API |
| `mock` | Placeholder PNG | No API key needed, for testing |

---

## Project Structure

```
script-to-image/
├── main.py                  # CLI entry point
├── config.py                # Environment config
├── requirements.txt
├── .env.example
├── models/
│   ├── character.py         # Character & CharacterSheet
│   ├── location.py          # Location & LocationSheet
│   └── script.py            # ScriptLine, Scene, Script (JSON + Fountain parser)
├── generators/
│   ├── prompt_generator.py  # Claude-powered prompt builder
│   └── image_generator.py   # Replicate / Stability AI / Mock backends
└── examples/
    ├── characters.json
    ├── locations.json
    ├── sample_script.json
    └── sample_script.fountain
```
