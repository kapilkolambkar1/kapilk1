"""Location model — describes where a scene takes place."""

from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class Location:
    name: str
    description: str                     # rich visual description
    time_of_day: Optional[str] = None    # e.g. "golden hour", "midnight", "noon"
    weather: Optional[str] = None        # e.g. "rainy", "clear sky", "foggy"
    mood: Optional[str] = None           # e.g. "ominous", "peaceful", "chaotic"
    art_style_tags: list[str] = field(default_factory=list)

    def to_prompt_fragment(self, time_override: Optional[str] = None) -> str:
        """Return a compact visual description for image prompt injection."""
        parts = [self.description]
        tod = time_override or self.time_of_day
        if tod:
            parts.append(tod)
        if self.weather:
            parts.append(self.weather)
        if self.mood:
            parts.append(f"{self.mood} atmosphere")
        if self.art_style_tags:
            parts.extend(self.art_style_tags)
        return ", ".join(parts)

    @classmethod
    def from_dict(cls, data: dict) -> "Location":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class LocationSheet:
    locations: dict[str, Location] = field(default_factory=dict)

    def add(self, location: Location) -> None:
        self.locations[location.name.lower()] = location

    def get(self, name: str) -> Optional[Location]:
        return self.locations.get(name.lower())

    @classmethod
    def from_json_file(cls, path: str) -> "LocationSheet":
        with open(path, "r") as f:
            data = json.load(f)
        sheet = cls()
        for entry in data:
            sheet.add(Location.from_dict(entry))
        return sheet
