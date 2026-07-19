"""
Prompt generator — uses Claude to turn a scene (dialog + characters + location)
into a vivid image generation prompt.
"""

import os
from typing import Optional
import anthropic

from models.character import CharacterSheet
from models.location import LocationSheet
from models.script import Scene


SYSTEM_PROMPT = """You are a cinematic storyboard artist and image prompt engineer.
Given a screenplay scene with dialog, character descriptions, and location details,
you produce concise, vivid image generation prompts optimized for Stable Diffusion / SDXL.

Rules:
- Output ONLY the image prompt — no explanation, no markdown, no labels.
- Lead with the most important visual element (characters, action, or location).
- Include: composition, lighting, mood, art style, quality tags.
- Max 120 words.
- Append quality boosters at the end: "highly detailed, cinematic lighting, 8k, award-winning".
- If multiple characters are present, describe their relative positions and interaction.
- Reflect the emotional tone of the dialog in the scene.
"""


class PromptGenerator:
    def __init__(self, api_key: Optional[str] = None):
        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ["ANTHROPIC_API_KEY"]
        )

    def generate(
        self,
        scene: Scene,
        characters: CharacterSheet,
        locations: LocationSheet,
        extra_style: str = "",
    ) -> str:
        """Generate an image prompt for the given scene."""
        location = locations.get(scene.location)
        location_desc = (
            location.to_prompt_fragment(time_override=scene.time_of_day)
            if location
            else f"{scene.location}, {scene.time_of_day or ''}"
        )

        char_descriptions = []
        for name in scene.characters:
            char = characters.get(name)
            if char:
                char_descriptions.append(f"{name}: {char.to_prompt_fragment()}")
            else:
                char_descriptions.append(name)

        dialog_summary = scene.dialog_summary() or "(no dialog)"

        user_message = f"""Scene ID: {scene.id}

LOCATION:
{location_desc}

CHARACTERS IN SCENE:
{chr(10).join(char_descriptions) if char_descriptions else "No named characters"}

DIALOG / ACTION:
{dialog_summary}

{f"EXTRA STYLE NOTES: {extra_style}" if extra_style else ""}

Generate a single image prompt for this scene."""

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()

    def generate_per_line(
        self,
        scene: Scene,
        characters: CharacterSheet,
        locations: LocationSheet,
        line_index: int,
        extra_style: str = "",
    ) -> str:
        """Generate an image prompt focused on a specific dialog line within a scene."""
        from models.script import ScriptLine

        target_line = scene.lines[line_index]
        context_lines = scene.lines[max(0, line_index - 3): line_index + 1]
        dialog_ctx = "\n".join(
            f"{l.character}: {l.text}" if l.type == "dialog" and l.character else f"[{l.text}]"
            for l in context_lines
        )

        location = locations.get(scene.location)
        location_desc = (
            location.to_prompt_fragment(time_override=scene.time_of_day)
            if location
            else scene.location
        )

        speaker = target_line.character or "unknown"
        char = characters.get(speaker)
        char_desc = char.to_prompt_fragment() if char else speaker

        emotion_hint = target_line.emotion or ""

        user_message = f"""LOCATION: {location_desc}

SPEAKER: {speaker} — {char_desc}
EMOTION/TONE: {emotion_hint or "infer from dialog"}

DIALOG CONTEXT (last few lines):
{dialog_ctx}

FOCAL LINE: "{target_line.text}"

{f"EXTRA STYLE NOTES: {extra_style}" if extra_style else ""}

Generate a single image prompt capturing this specific moment."""

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()
