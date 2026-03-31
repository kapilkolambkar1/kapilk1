"""Script model — scenes composed of dialog lines and action beats."""

from dataclasses import dataclass, field
from typing import Optional
import json
import re


@dataclass
class ScriptLine:
    type: str           # "dialog" | "action" | "scene_heading"
    character: Optional[str] = None   # speaker name (dialog lines only)
    text: str = ""
    emotion: Optional[str] = None     # optional hint: "angry", "whispering"
    generate_image: bool = False       # flag to force image gen for this line

    @classmethod
    def from_dict(cls, data: dict) -> "ScriptLine":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Scene:
    id: str
    location: str                              # key into LocationSheet
    time_of_day: Optional[str] = None
    characters: list[str] = field(default_factory=list)  # character names present
    lines: list[ScriptLine] = field(default_factory=list)
    generate_image: bool = True                # generate at least one image per scene

    @classmethod
    def from_dict(cls, data: dict) -> "Scene":
        lines = [ScriptLine.from_dict(l) for l in data.pop("lines", [])]
        characters = data.pop("characters", [])
        obj = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        obj.lines = lines
        obj.characters = characters
        return obj

    def dialog_summary(self) -> str:
        """Return a condensed dialog summary for prompt context."""
        parts = []
        for line in self.lines:
            if line.type == "dialog" and line.character:
                parts.append(f"{line.character}: {line.text}")
            elif line.type == "action":
                parts.append(f"[{line.text}]")
        return "\n".join(parts)


@dataclass
class Script:
    title: str
    scenes: list[Scene] = field(default_factory=list)

    @classmethod
    def from_json_file(cls, path: str) -> "Script":
        with open(path, "r") as f:
            data = json.load(f)
        scenes = [Scene.from_dict(s) for s in data.get("scenes", [])]
        script = cls(title=data.get("title", "Untitled"))
        script.scenes = scenes
        return script

    @classmethod
    def from_fountain_file(cls, path: str) -> "Script":
        """Basic Fountain screenplay parser → Script object."""
        with open(path, "r") as f:
            raw = f.read()
        return cls._parse_fountain(raw, title=path)

    @classmethod
    def _parse_fountain(cls, raw: str, title: str = "Untitled") -> "Script":
        scenes: list[Scene] = []
        current_scene: Optional[Scene] = None
        scene_counter = 0

        for line in raw.splitlines():
            line = line.rstrip()

            # Scene heading: INT./EXT.
            if re.match(r"^(INT\.|EXT\.|INT/EXT\.|I/E\.)", line, re.IGNORECASE):
                if current_scene:
                    scenes.append(current_scene)
                scene_counter += 1
                location = re.sub(r"^(INT\.|EXT\.|INT/EXT\.|I/E\.)\s*", "", line, flags=re.IGNORECASE)
                location = re.split(r"\s+-\s+", location)[0].strip()
                current_scene = Scene(
                    id=f"scene_{scene_counter}",
                    location=location.lower(),
                )
                current_scene.lines.append(
                    ScriptLine(type="scene_heading", text=line)
                )

            elif current_scene is None:
                continue

            # All-caps line = character name
            elif re.match(r"^[A-Z][A-Z\s]+$", line) and line.strip():
                current_scene.characters.append(line.strip().title())

            # Parenthetical
            elif line.startswith("(") and line.endswith(")"):
                current_scene.lines.append(
                    ScriptLine(type="action", text=line.strip("()"))
                )

            # Non-empty = dialog if last token was a character
            elif line.strip() and current_scene.characters:
                speaker = current_scene.characters[-1] if current_scene.characters else None
                current_scene.lines.append(
                    ScriptLine(type="dialog", character=speaker, text=line.strip())
                )

            # Empty lines = action beats
            elif not line.strip():
                pass

        if current_scene:
            scenes.append(current_scene)

        script = cls(title=title)
        script.scenes = scenes
        return script
