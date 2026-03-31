#!/usr/bin/env python3
"""
Script-to-Image Generator
=========================
Converts screenplay scripts (JSON or Fountain .fountain) into AI-generated images
using character sheets, location descriptions, and Claude + Stable Diffusion.

Usage:
  python main.py generate --script examples/sample_script.json \
                          --characters examples/characters.json \
                          --locations examples/locations.json \
                          --backend mock

  python main.py generate --script myscript.fountain \
                          --characters chars.json \
                          --locations locs.json \
                          --backend replicate
"""

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

load_dotenv()

console = Console()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """Script-to-Image Generator — turn screenplays into storyboard images."""


@cli.command()
@click.option("--script", "-s", required=True, type=click.Path(exists=True), help="Script file (.json or .fountain)")
@click.option("--characters", "-c", required=True, type=click.Path(exists=True), help="Character sheet JSON")
@click.option("--locations", "-l", required=True, type=click.Path(exists=True), help="Location sheet JSON")
@click.option("--output", "-o", default="output", help="Output directory for images")
@click.option("--backend", "-b", default=None, type=click.Choice(["replicate", "stability", "mock"]),
              help="Image generation backend (default: from .env or 'mock')")
@click.option("--style", default="", help="Extra style tags appended to every prompt")
@click.option("--per-line", is_flag=True, default=False,
              help="Generate one image per dialog line (instead of one per scene)")
@click.option("--scene", "scene_filter", default=None, help="Only process this scene ID")
@click.option("--dry-run", is_flag=True, default=False, help="Print prompts without generating images")
def generate(script, characters, locations, output, backend, style, per_line, scene_filter, dry_run):
    """Generate images from a screenplay script."""

    # Lazy imports so CLI help loads fast
    from models import CharacterSheet, LocationSheet, Script
    from generators import PromptGenerator, ImageGenerator

    console.print(Panel.fit("[bold cyan]Script-to-Image Generator[/bold cyan]", border_style="cyan"))

    # Load assets
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as p:
        t = p.add_task("Loading character sheet...", total=None)
        char_sheet = CharacterSheet.from_json_file(characters)
        p.update(t, description=f"[green]Loaded {len(char_sheet.characters)} characters")

        p.add_task("Loading location sheet...", total=None)
        loc_sheet = LocationSheet.from_json_file(locations)

        t2 = p.add_task("Parsing script...", total=None)
        if script.endswith(".fountain"):
            scr = Script.from_fountain_file(script)
        else:
            scr = Script.from_json_file(script)
        p.update(t2, description=f"[green]Parsed '{scr.title}' — {len(scr.scenes)} scene(s)")

    console.print(f"\n[bold]Script:[/bold] {scr.title}")
    console.print(f"[bold]Characters:[/bold] {', '.join(char_sheet.characters.keys())}")
    console.print(f"[bold]Locations:[/bold] {', '.join(loc_sheet.locations.keys())}")
    console.print(f"[bold]Backend:[/bold] {backend or os.environ.get('IMAGE_BACKEND', 'mock')}\n")

    # Build generators
    prompt_gen = PromptGenerator()
    img_gen = ImageGenerator(backend=backend, output_dir=output) if not dry_run else None

    results = []
    scenes_to_process = [s for s in scr.scenes if not scene_filter or s.id == scene_filter]

    for scene in scenes_to_process:
        console.rule(f"[bold yellow]{scene.id}[/bold yellow] — {scene.location}")

        if per_line:
            dialog_lines = [
                (i, line) for i, line in enumerate(scene.lines)
                if line.type == "dialog" or line.generate_image
            ]
            for line_idx, line in dialog_lines:
                label = f"{line.character}: {line.text[:60]}..." if len(line.text) > 60 else f"{line.character}: {line.text}"
                console.print(f"  [dim]{label}[/dim]")

                with console.status("  Generating prompt..."):
                    prompt = prompt_gen.generate_per_line(scene, char_sheet, loc_sheet, line_idx, style)

                console.print(f"  [bold green]Prompt:[/bold green] {prompt[:120]}...")

                if not dry_run:
                    with console.status("  Generating image..."):
                        img_path = img_gen.generate(prompt, scene_id=f"{scene.id}_line{line_idx}")
                    console.print(f"  [bold blue]Saved:[/bold blue] {img_path}")
                    results.append({"scene": scene.id, "line": line_idx, "prompt": prompt, "image": str(img_path)})
                else:
                    results.append({"scene": scene.id, "line": line_idx, "prompt": prompt, "image": "(dry run)"})
        else:
            with console.status("  Generating scene prompt..."):
                prompt = prompt_gen.generate(scene, char_sheet, loc_sheet, style)

            console.print(f"  [bold green]Prompt:[/bold green] {prompt[:140]}...")

            if not dry_run:
                with console.status("  Generating image..."):
                    img_path = img_gen.generate(prompt, scene_id=scene.id)
                console.print(f"  [bold blue]Saved:[/bold blue] {img_path}")
                results.append({"scene": scene.id, "prompt": prompt, "image": str(img_path)})
            else:
                results.append({"scene": scene.id, "prompt": prompt, "image": "(dry run)"})

    # Summary table
    table = Table(title="\nGeneration Summary", show_lines=True)
    table.add_column("Scene", style="cyan")
    table.add_column("Image", style="green")
    table.add_column("Prompt (truncated)", style="dim")
    for r in results:
        table.add_row(r["scene"], r.get("image", ""), r["prompt"][:80] + "...")
    console.print(table)
    console.print(f"\n[bold green]Done![/bold green] {len(results)} image(s) generated → {output}/")


@cli.command()
@click.option("--characters", "-c", required=True, type=click.Path(exists=True))
@click.option("--locations", "-l", required=True, type=click.Path(exists=True))
def inspect(characters, locations):
    """Print all loaded characters and locations."""
    from models import CharacterSheet, LocationSheet

    char_sheet = CharacterSheet.from_json_file(characters)
    loc_sheet = LocationSheet.from_json_file(locations)

    t = Table(title="Characters", show_lines=True)
    t.add_column("Name", style="cyan")
    t.add_column("Visual Description")
    for name, char in char_sheet.characters.items():
        t.add_row(name.title(), char.to_prompt_fragment())
    console.print(t)

    t2 = Table(title="Locations", show_lines=True)
    t2.add_column("Name", style="yellow")
    t2.add_column("Description")
    for name, loc in loc_sheet.locations.items():
        t2.add_row(name.title(), loc.to_prompt_fragment())
    console.print(t2)


if __name__ == "__main__":
    cli()
