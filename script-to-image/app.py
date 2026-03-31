"""
Script-to-Image Generator — Streamlit GUI
==========================================
Run:
    cd script-to-image
    streamlit run app.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from PIL import Image

# Make sure local modules are importable from anywhere
sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(Path(__file__).parent / ".env")

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Script-to-Image Generator",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .scene-card {
        background: #1e1e2e;
        border: 1px solid #313244;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .prompt-box {
        background: #181825;
        border-left: 3px solid #89b4fa;
        padding: 10px 14px;
        border-radius: 0 6px 6px 0;
        font-size: 0.85em;
        color: #cdd6f4;
        margin-top: 8px;
    }
    .character-chip {
        display: inline-block;
        background: #313244;
        color: #cba6f7;
        border-radius: 12px;
        padding: 2px 10px;
        margin: 2px;
        font-size: 0.8em;
    }
    .dialog-line {
        border-left: 2px solid #45475a;
        padding-left: 10px;
        margin: 4px 0;
        color: #bac2de;
        font-size: 0.88em;
    }
    .action-line {
        color: #6c7086;
        font-style: italic;
        font-size: 0.85em;
    }
    h1, h2, h3 { color: #cdd6f4 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
def _init_state():
    defaults = {
        "char_sheet": None,
        "loc_sheet": None,
        "script": None,
        "results": [],          # list of {scene_id, prompt, image_path}
        "anthropic_key": os.environ.get("ANTHROPIC_API_KEY", ""),
        "replicate_token": os.environ.get("REPLICATE_API_TOKEN", ""),
        "stability_key": os.environ.get("STABILITY_API_KEY", ""),
        "backend": os.environ.get("IMAGE_BACKEND", "mock"),
        "extra_style": "",
        "per_line": False,
        "generating": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
EXAMPLES_DIR = Path(__file__).parent / "examples"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def _load_char_sheet(data: list | None = None, path: str | None = None):
    from models.character import CharacterSheet, Character
    if path:
        return CharacterSheet.from_json_file(path)
    if data:
        sheet = CharacterSheet()
        for entry in data:
            sheet.add(Character.from_dict(entry))
        return sheet
    return None


def _load_loc_sheet(data: list | None = None, path: str | None = None):
    from models.location import LocationSheet, Location
    if path:
        return LocationSheet.from_json_file(path)
    if data:
        sheet = LocationSheet()
        for entry in data:
            sheet.add(Location.from_dict(entry))
        return sheet
    return None


def _load_script(data: dict | None = None, path: str | None = None, fountain: bool = False):
    from models.script import Script
    if path and fountain:
        return Script.from_fountain_file(path)
    if path:
        return Script.from_json_file(path)
    if data:
        from models.script import Scene, ScriptLine
        scenes = [Scene.from_dict(s) for s in data.get("scenes", [])]
        scr = Script(title=data.get("title", "Untitled"))
        scr.scenes = scenes
        return scr
    return None


def _read_uploaded(uploaded_file) -> str:
    """Save uploaded file to a temp file and return the path."""
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(uploaded_file.read())
        return f.name


# ---------------------------------------------------------------------------
# Sidebar — Configuration
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🎬 Script-to-Image")
    st.caption("AI storyboard generator")
    st.divider()

    st.subheader("🔑 API Keys")
    st.session_state.anthropic_key = st.text_input(
        "Anthropic API Key", value=st.session_state.anthropic_key,
        type="password", placeholder="sk-ant-..."
    )
    st.session_state.replicate_token = st.text_input(
        "Replicate Token", value=st.session_state.replicate_token,
        type="password", placeholder="r8_..."
    )
    st.session_state.stability_key = st.text_input(
        "Stability AI Key", value=st.session_state.stability_key,
        type="password", placeholder="sk-..."
    )

    st.divider()
    st.subheader("⚙️ Settings")
    st.session_state.backend = st.selectbox(
        "Image Backend",
        ["mock", "replicate", "stability"],
        index=["mock", "replicate", "stability"].index(st.session_state.backend),
        help="'mock' generates placeholder images without any API key.",
    )
    st.session_state.extra_style = st.text_input(
        "Extra Style Tags",
        value=st.session_state.extra_style,
        placeholder="e.g. watercolor, anime, oil painting",
    )
    st.session_state.per_line = st.toggle(
        "One image per dialog line",
        value=st.session_state.per_line,
        help="Generates more images but uses more API credits.",
    )

    st.divider()
    # Status indicators
    has_anthropic = bool(st.session_state.anthropic_key)
    has_img = (
        st.session_state.backend == "mock"
        or (st.session_state.backend == "replicate" and bool(st.session_state.replicate_token))
        or (st.session_state.backend == "stability" and bool(st.session_state.stability_key))
    )
    st.markdown(
        f"{'✅' if has_anthropic else '❌'} Prompt generation (Claude)  \n"
        f"{'✅' if has_img else '❌'} Image generation ({st.session_state.backend})"
    )

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_setup, tab_generate, tab_gallery, tab_editor = st.tabs(
    ["📂 Load Assets", "🎨 Generate", "🖼️ Gallery", "✏️ Editor"]
)

# ===========================================================================
# TAB 1 — Load Assets
# ===========================================================================
with tab_setup:
    st.header("Load Script & Assets")

    col_left, col_right = st.columns(2, gap="large")

    # ---- Characters --------------------------------------------------------
    with col_left:
        st.subheader("🧑 Characters")
        char_src = st.radio(
            "Source", ["Use example", "Upload JSON"],
            horizontal=True, key="char_src"
        )
        if char_src == "Use example":
            if st.button("Load example characters", key="btn_load_chars"):
                st.session_state.char_sheet = _load_char_sheet(
                    path=str(EXAMPLES_DIR / "characters.json")
                )
                st.success(f"Loaded {len(st.session_state.char_sheet.characters)} characters")
        else:
            uploaded_chars = st.file_uploader("characters.json", type=["json"], key="up_chars")
            if uploaded_chars and st.button("Load uploaded characters"):
                tmp = _read_uploaded(uploaded_chars)
                st.session_state.char_sheet = _load_char_sheet(path=tmp)
                st.success(f"Loaded {len(st.session_state.char_sheet.characters)} characters")

        if st.session_state.char_sheet:
            for name, char in st.session_state.char_sheet.characters.items():
                with st.expander(f"👤 {name.title()}"):
                    frag = char.to_prompt_fragment()
                    st.caption(frag)
                    if char.distinguishing_features:
                        st.markdown("**Features:** " + ", ".join(char.distinguishing_features))
                    if char.art_style_tags:
                        st.markdown("**Style tags:** " + ", ".join(char.art_style_tags))

    # ---- Locations ---------------------------------------------------------
    with col_right:
        st.subheader("🏙️ Locations")
        loc_src = st.radio(
            "Source", ["Use example", "Upload JSON"],
            horizontal=True, key="loc_src"
        )
        if loc_src == "Use example":
            if st.button("Load example locations", key="btn_load_locs"):
                st.session_state.loc_sheet = _load_loc_sheet(
                    path=str(EXAMPLES_DIR / "locations.json")
                )
                st.success(f"Loaded {len(st.session_state.loc_sheet.locations)} locations")
        else:
            uploaded_locs = st.file_uploader("locations.json", type=["json"], key="up_locs")
            if uploaded_locs and st.button("Load uploaded locations"):
                tmp = _read_uploaded(uploaded_locs)
                st.session_state.loc_sheet = _load_loc_sheet(path=tmp)
                st.success(f"Loaded {len(st.session_state.loc_sheet.locations)} locations")

        if st.session_state.loc_sheet:
            for name, loc in st.session_state.loc_sheet.locations.items():
                with st.expander(f"📍 {name.title()}"):
                    st.caption(loc.description)
                    cols = st.columns(3)
                    cols[0].metric("Time", loc.time_of_day or "—")
                    cols[1].metric("Weather", loc.weather or "—")
                    cols[2].metric("Mood", loc.mood or "—")

    st.divider()

    # ---- Script ------------------------------------------------------------
    st.subheader("📜 Script")
    script_src = st.radio(
        "Source", ["Use example (JSON)", "Use example (Fountain)", "Upload"],
        horizontal=True, key="script_src"
    )

    if script_src == "Use example (JSON)":
        if st.button("Load example script (JSON)", key="btn_load_script_json"):
            st.session_state.script = _load_script(
                path=str(EXAMPLES_DIR / "sample_script.json")
            )
            st.success(f"Loaded '{st.session_state.script.title}' — {len(st.session_state.script.scenes)} scenes")

    elif script_src == "Use example (Fountain)":
        if st.button("Load example script (Fountain)", key="btn_load_script_ftn"):
            st.session_state.script = _load_script(
                path=str(EXAMPLES_DIR / "sample_script.fountain"), fountain=True
            )
            st.success(f"Loaded '{st.session_state.script.title}' — {len(st.session_state.script.scenes)} scenes")

    else:
        uploaded_script = st.file_uploader(
            "Script file", type=["json", "fountain"], key="up_script"
        )
        if uploaded_script and st.button("Load uploaded script"):
            tmp = _read_uploaded(uploaded_script)
            is_fountain = uploaded_script.name.endswith(".fountain")
            st.session_state.script = _load_script(path=tmp, fountain=is_fountain)
            st.success(f"Loaded '{st.session_state.script.title}' — {len(st.session_state.script.scenes)} scenes")

    if st.session_state.script:
        st.markdown(f"### {st.session_state.script.title}")
        for scene in st.session_state.script.scenes:
            with st.expander(f"🎬 {scene.id} — {scene.location.title()}"):
                if scene.characters:
                    chars_html = "".join(
                        f'<span class="character-chip">{c}</span>'
                        for c in scene.characters
                    )
                    st.markdown(f"**Characters:** {chars_html}", unsafe_allow_html=True)
                for line in scene.lines:
                    if line.type == "dialog" and line.character:
                        st.markdown(
                            f'<div class="dialog-line"><strong>{line.character}:</strong> {line.text}</div>',
                            unsafe_allow_html=True,
                        )
                    elif line.type == "action":
                        st.markdown(
                            f'<div class="action-line">[{line.text}]</div>',
                            unsafe_allow_html=True,
                        )

# ===========================================================================
# TAB 2 — Generate
# ===========================================================================
with tab_generate:
    st.header("Generate Images")

    ready = (
        st.session_state.char_sheet is not None
        and st.session_state.loc_sheet is not None
        and st.session_state.script is not None
    )

    if not ready:
        st.info("Load characters, locations, and a script in the **Load Assets** tab first.")
    else:
        st.markdown(
            f"**Script:** {st.session_state.script.title} &nbsp;|&nbsp; "
            f"**Scenes:** {len(st.session_state.script.scenes)} &nbsp;|&nbsp; "
            f"**Backend:** `{st.session_state.backend}`"
        )

        # Scene filter
        scene_ids = ["All scenes"] + [s.id for s in st.session_state.script.scenes]
        chosen_scene = st.selectbox("Scene to generate", scene_ids)

        col_gen, col_dry = st.columns([1, 1])
        generate_btn = col_gen.button("🚀 Generate", type="primary", use_container_width=True)
        dry_run_btn = col_dry.button("🔍 Dry Run (prompts only)", use_container_width=True)

        if generate_btn or dry_run_btn:
            dry_run = dry_run_btn

            # Inject API keys into env for generators
            if st.session_state.anthropic_key:
                os.environ["ANTHROPIC_API_KEY"] = st.session_state.anthropic_key
            if st.session_state.replicate_token:
                os.environ["REPLICATE_API_TOKEN"] = st.session_state.replicate_token
            if st.session_state.stability_key:
                os.environ["STABILITY_API_KEY"] = st.session_state.stability_key

            try:
                from generators import PromptGenerator, ImageGenerator

                prompt_gen = PromptGenerator()
                img_gen = ImageGenerator(
                    backend=st.session_state.backend,
                    output_dir=str(OUTPUT_DIR),
                ) if not dry_run else None

                scenes_to_run = (
                    st.session_state.script.scenes
                    if chosen_scene == "All scenes"
                    else [s for s in st.session_state.script.scenes if s.id == chosen_scene]
                )

                new_results = []
                total = len(scenes_to_run)
                progress_bar = st.progress(0, text="Starting...")

                for idx, scene in enumerate(scenes_to_run):
                    progress_bar.progress(
                        idx / total,
                        text=f"Processing {scene.id} ({idx + 1}/{total})…",
                    )

                    if st.session_state.per_line:
                        dialog_indices = [
                            i for i, l in enumerate(scene.lines)
                            if l.type == "dialog" or l.generate_image
                        ]
                        for li in dialog_indices:
                            with st.spinner(f"Generating prompt for {scene.id} line {li}…"):
                                prompt = prompt_gen.generate_per_line(
                                    scene,
                                    st.session_state.char_sheet,
                                    st.session_state.loc_sheet,
                                    li,
                                    st.session_state.extra_style,
                                )
                            img_path = None
                            if not dry_run:
                                with st.spinner("Generating image…"):
                                    img_path = img_gen.generate(
                                        prompt, scene_id=f"{scene.id}_l{li}"
                                    )
                            new_results.append({
                                "scene_id": scene.id,
                                "line": li,
                                "character": scene.lines[li].character,
                                "dialog": scene.lines[li].text,
                                "prompt": prompt,
                                "image_path": str(img_path) if img_path else None,
                            })
                    else:
                        with st.spinner(f"Generating prompt for {scene.id}…"):
                            prompt = prompt_gen.generate(
                                scene,
                                st.session_state.char_sheet,
                                st.session_state.loc_sheet,
                                st.session_state.extra_style,
                            )
                        img_path = None
                        if not dry_run:
                            with st.spinner(f"Generating image for {scene.id}…"):
                                img_path = img_gen.generate(prompt, scene_id=scene.id)
                        new_results.append({
                            "scene_id": scene.id,
                            "line": None,
                            "character": None,
                            "dialog": scene.dialog_summary(),
                            "prompt": prompt,
                            "image_path": str(img_path) if img_path else None,
                        })

                progress_bar.progress(1.0, text="Done!")
                st.session_state.results.extend(new_results)
                st.success(f"Generated {len(new_results)} result(s)!")

            except Exception as e:
                st.error(f"Error: {e}")
                st.exception(e)

        # Show results
        if st.session_state.results:
            st.divider()
            st.subheader("Results")

            for r in reversed(st.session_state.results):
                with st.container():
                    c1, c2 = st.columns([1, 1], gap="medium")

                    with c1:
                        if r["image_path"] and Path(r["image_path"]).exists():
                            img = Image.open(r["image_path"])
                            st.image(img, caption=r["scene_id"], use_container_width=True)
                        else:
                            st.info("No image (dry run)")

                    with c2:
                        st.markdown(f"**Scene:** `{r['scene_id']}`")
                        if r["character"]:
                            st.markdown(f"**Character:** {r['character']}")
                        if r["dialog"]:
                            st.markdown("**Dialog:**")
                            for dline in r["dialog"].splitlines()[:4]:
                                st.markdown(
                                    f'<div class="dialog-line">{dline}</div>',
                                    unsafe_allow_html=True,
                                )
                        st.markdown("**Generated Prompt:**")
                        st.markdown(
                            f'<div class="prompt-box">{r["prompt"]}</div>',
                            unsafe_allow_html=True,
                        )
                        if r["image_path"]:
                            with open(r["image_path"], "rb") as f:
                                st.download_button(
                                    "⬇️ Download",
                                    f,
                                    file_name=Path(r["image_path"]).name,
                                    mime="image/png",
                                    key=f"dl_{r['image_path']}",
                                )
                    st.divider()

            if st.button("🗑️ Clear Results"):
                st.session_state.results = []
                st.rerun()

# ===========================================================================
# TAB 3 — Gallery
# ===========================================================================
with tab_gallery:
    st.header("🖼️ Gallery")

    png_files = sorted(OUTPUT_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not png_files:
        st.info("No images generated yet. Use the **Generate** tab to create some.")
    else:
        st.caption(f"{len(png_files)} image(s) in `output/`")

        # 3-column grid
        cols = st.columns(3)
        for i, img_path in enumerate(png_files):
            with cols[i % 3]:
                img = Image.open(img_path)
                st.image(img, caption=img_path.stem, use_container_width=True)
                with open(img_path, "rb") as f:
                    st.download_button(
                        "⬇️",
                        f,
                        file_name=img_path.name,
                        mime="image/png",
                        key=f"gal_dl_{img_path.name}",
                    )

        st.divider()
        if st.button("🗑️ Delete all images", type="secondary"):
            for p in png_files:
                p.unlink()
            st.success("Gallery cleared.")
            st.rerun()

# ===========================================================================
# TAB 4 — Inline Editor
# ===========================================================================
with tab_editor:
    st.header("✏️ Inline JSON Editor")
    st.caption("Edit character sheets, locations, or scripts directly and reload them.")

    edit_target = st.radio(
        "Edit", ["Characters", "Locations", "Script"],
        horizontal=True
    )

    example_map = {
        "Characters": EXAMPLES_DIR / "characters.json",
        "Locations": EXAMPLES_DIR / "locations.json",
        "Script": EXAMPLES_DIR / "sample_script.json",
    }

    default_text = example_map[edit_target].read_text() if example_map[edit_target].exists() else "{}"

    edited = st.text_area(
        f"Edit {edit_target} JSON",
        value=default_text,
        height=420,
        key=f"editor_{edit_target}",
    )

    col_a, col_b = st.columns(2)
    if col_a.button(f"✅ Load edited {edit_target}", type="primary"):
        try:
            data = json.loads(edited)
            if edit_target == "Characters":
                st.session_state.char_sheet = _load_char_sheet(data=data)
                st.success(f"Loaded {len(st.session_state.char_sheet.characters)} characters")
            elif edit_target == "Locations":
                st.session_state.loc_sheet = _load_loc_sheet(data=data)
                st.success(f"Loaded {len(st.session_state.loc_sheet.locations)} locations")
            else:
                st.session_state.script = _load_script(data=data)
                st.success(f"Loaded '{st.session_state.script.title}' — {len(st.session_state.script.scenes)} scenes")
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {e}")
        except Exception as e:
            st.error(f"Load error: {e}")

    if col_b.button("💾 Save to examples folder"):
        try:
            json.loads(edited)  # validate first
            example_map[edit_target].write_text(edited)
            st.success(f"Saved to {example_map[edit_target]}")
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {e}")
