"""Character sheet model — describes physical appearance, style, and traits."""

from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class Character:
    name: str
    age: Optional[str] = None            # e.g. "mid-30s", "teenager"
    gender: Optional[str] = None
    ethnicity: Optional[str] = None
    build: Optional[str] = None          # e.g. "athletic", "slim", "heavy-set"
    hair: Optional[str] = None           # color + style
    eyes: Optional[str] = None
    skin: Optional[str] = None
    clothing_style: Optional[str] = None # e.g. "business casual", "fantasy armor"
    distinguishing_features: list[str] = field(default_factory=list)
    personality: Optional[str] = None    # brief for emotion/pose hints
    art_style_tags: list[str] = field(default_factory=list)  # extra SD tags

    def to_prompt_fragment(self) -> str:
        """Return a compact visual description suitable for injection into an image prompt."""
        parts = []
        if self.gender:
            parts.append(self.gender)
        if self.age:
            parts.append(self.age)
        if self.ethnicity:
            parts.append(self.ethnicity)
        if self.build:
            parts.append(f"{self.build} build")
        if self.hair:
            parts.append(f"{self.hair} hair")
        if self.eyes:
            parts.append(f"{self.eyes} eyes")
        if self.skin:
            parts.append(f"{self.skin} skin")
        if self.clothing_style:
            parts.append(f"wearing {self.clothing_style}")
        if self.distinguishing_features:
            parts.extend(self.distinguishing_features)
        if self.art_style_tags:
            parts.extend(self.art_style_tags)
        return ", ".join(parts)

    @classmethod
    def from_dict(cls, data: dict) -> "Character":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CharacterSheet:
    characters: dict[str, Character] = field(default_factory=dict)

    def add(self, character: Character) -> None:
        self.characters[character.name.lower()] = character

    def get(self, name: str) -> Optional[Character]:
        return self.characters.get(name.lower())

    @classmethod
    def from_json_file(cls, path: str) -> "CharacterSheet":
        with open(path, "r") as f:
            data = json.load(f)
        sheet = cls()
        for entry in data:
            sheet.add(Character.from_dict(entry))
        return sheet
