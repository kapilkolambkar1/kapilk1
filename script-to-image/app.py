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
        # Character Canvas approval state
        "canvas_chars": [],        # list of dicts per character
        "canvas_analyzed": False,
        # Google Sheet push state
        "gsheet_url": "",          # URL of last created sheet
        "scene_image_results": [], # list of dicts from SceneImagePusher
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
tab_setup, tab_generate, tab_sheet, tab_export, tab_gallery, tab_editor = st.tabs(
    ["📂 Load Assets", "🎨 Generate", "📋 Image Sheet", "📊 Google Sheets", "🖼️ Gallery", "✏️ Editor"]
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
# TAB 3 — Image Sheet  (Pollinations.ai — free, no API key required)
# ===========================================================================
with tab_sheet:
    st.header("📋 Image Sheet")
    st.caption(
        "Generates a single storyboard contact sheet — one image per scene — "
        "using **[Pollinations.ai](https://pollinations.ai)** (free, no API key required)."
    )

    sheet_ready = (
        st.session_state.char_sheet is not None
        and st.session_state.loc_sheet is not None
        and st.session_state.script is not None
    )

    if not sheet_ready:
        st.info("Load characters, locations, and a script in the **Load Assets** tab first.")
    else:
        c1, c2 = st.columns(2)

        scene_ids_sheet = ["All scenes"] + [s.id for s in st.session_state.script.scenes]
        sheet_scene = c1.selectbox("Scenes", scene_ids_sheet, key="sheet_scene_sel")
        sheet_cols = c2.slider("Columns per row", 1, 5, 3, key="sheet_cols")

        c3, c4 = st.columns(2)
        sheet_per_line = c3.toggle("One frame per dialog line", key="sheet_per_line")
        sheet_model = c4.selectbox(
            "Pollinations model",
            ["flux", "flux-realism", "flux-anime", "flux-3d", "turbo"],
            key="sheet_model",
            help="flux = best quality · turbo = fastest",
        )

        sheet_style = st.text_input(
            "Extra style tags (appended to every prompt)",
            value=st.session_state.extra_style,
            key="sheet_style",
            placeholder="e.g. watercolor, noir, anime",
        )

        sheet_seed = st.number_input(
            "Seed (0 = random)", min_value=0, max_value=2**31, value=0, key="sheet_seed"
        )

        if st.button("🎬 Build Image Sheet", type="primary", use_container_width=True):
            if st.session_state.anthropic_key:
                os.environ["ANTHROPIC_API_KEY"] = st.session_state.anthropic_key

            try:
                from generators.image_sheet import ImageSheetGenerator

                gen = ImageSheetGenerator(
                    anthropic_api_key=st.session_state.anthropic_key,
                    cols=sheet_cols,
                )

                progress_bar = st.progress(0, text="Starting…")
                status_text = st.empty()

                def _on_progress(current, total, label):
                    pct = current / max(total, 1)
                    progress_bar.progress(pct, text=label)
                    status_text.caption(label)

                sheet_path = gen.build(
                    script=st.session_state.script,
                    characters=st.session_state.char_sheet,
                    locations=st.session_state.loc_sheet,
                    output_dir=str(OUTPUT_DIR),
                    extra_style=sheet_style,
                    per_line=sheet_per_line,
                    scene_filter=None if sheet_scene == "All scenes" else sheet_scene,
                    pollinations_model=sheet_model,
                    seed=int(sheet_seed) if sheet_seed > 0 else None,
                    on_progress=_on_progress,
                )

                progress_bar.progress(1.0, text="Done!")
                status_text.empty()

                st.success(f"Sheet saved: `{sheet_path.name}`")
                sheet_img = Image.open(sheet_path)
                st.image(sheet_img, caption=sheet_path.name, use_container_width=True)

                with open(sheet_path, "rb") as f:
                    st.download_button(
                        "⬇️ Download Sheet PNG",
                        f,
                        file_name=sheet_path.name,
                        mime="image/png",
                        type="primary",
                    )

            except Exception as e:
                st.error(f"Error building sheet: {e}")
                st.exception(e)

# ===========================================================================
# TAB 4 — Google Sheets / CSV Export
# ===========================================================================
with tab_export:
    st.header("📊 Google Sheets Export")
    st.caption(
        "Breaks the script into rows — one row per dialog line or action beat — "
        "and exports to **Google Sheets** or downloads as **CSV**."
    )

    if st.session_state.script is None:
        st.info("Load a script in the **Load Assets** tab first.")
    else:
        script = st.session_state.script

        # ── Live preview ────────────────────────────────────────────────
        st.subheader("Preview")

        from generators.sheets_exporter import _build_rows, COLUMNS
        preview_rows = _build_rows(script)

        import pandas as pd

        df = pd.DataFrame([r.as_list() for r in preview_rows], columns=COLUMNS)

        # Colour-code the dataframe by line type for display
        def _row_style(row):
            t = row["Type"]
            if t == "SCENE HEADING":
                return ["background-color: #2c3e50; color: #ecf0f1"] * len(row)
            elif t == "ACTION":
                return ["background-color: #f2f3f4"] * len(row)
            else:
                return [""] * len(row)

        st.dataframe(
            df.style.apply(_row_style, axis=1),
            use_container_width=True,
            height=380,
        )
        st.caption(f"{len(preview_rows)} rows · {len(script.scenes)} scenes")

        st.divider()

        # ── Character Canvas — analysis + approval ───────────────────────
        st.subheader("🎭 Character Canvas (Sheet Tab 2)")
        st.caption(
            "Analyze the script to extract every character, enrich from the "
            "character sheet, add an **Image URL**, then **approve** each one "
            "before it gets pushed to Google Sheets."
        )

        col_analyze, col_reset = st.columns([2, 1])
        if col_analyze.button("🔍 Analyze Script for Characters", use_container_width=True):
            from generators.sheets_exporter import build_character_canvas_rows

            raw_rows = build_character_canvas_rows(
                script=script,
                char_sheet=st.session_state.char_sheet,
            )

            # Merge into session state, preserving any image URLs already entered
            existing = {c["name"]: c for c in st.session_state.canvas_chars}
            merged = []
            for row in raw_rows:
                prev = existing.get(row.name, {})
                merged.append({
                    "name": row.name,
                    "age": row.age,
                    "gender": row.gender,
                    "ethnicity": row.ethnicity,
                    "build": row.build,
                    "hair": row.hair,
                    "eyes": row.eyes,
                    "skin": row.skin,
                    "clothing_style": row.clothing_style,
                    "distinguishing_features": row.distinguishing_features,
                    "personality": row.personality,
                    "art_style_tags": row.art_style_tags,
                    "visual_description": row.visual_description,
                    "scenes_appears_in": row.scenes_appears_in,
                    "image_url": prev.get("image_url", ""),
                    "notes": prev.get("notes", ""),
                    "approved": prev.get("approved", True),
                })
            st.session_state.canvas_chars = merged
            st.session_state.canvas_analyzed = True
            st.rerun()

        if col_reset.button("🗑️ Reset", use_container_width=True):
            st.session_state.canvas_chars = []
            st.session_state.canvas_analyzed = False
            st.rerun()

        if st.session_state.canvas_analyzed and st.session_state.canvas_chars:
            st.markdown(
                f"Found **{len(st.session_state.canvas_chars)} character(s)**. "
                "Fill in the Image URL for each and tick **Approve** to include them in the sheet."
            )

            # Palette for card borders (mirrors CHARACTER_COLORS)
            _CARD_COLORS = [
                "#D0E8FF", "#D5F5E3", "#FAD7A0", "#E8DAEF",
                "#FDEBD0", "#D6EAF8", "#FDEDEC", "#E9F7EF",
            ]

            updated_chars = []
            for idx, char in enumerate(st.session_state.canvas_chars):
                border_color = _CARD_COLORS[idx % len(_CARD_COLORS)]

                st.markdown(
                    f'<div style="border-left:4px solid {border_color};'
                    f'padding:8px 14px;margin-bottom:6px;border-radius:0 8px 8px 0;'
                    f'background:#1e1e2e;">',
                    unsafe_allow_html=True,
                )

                hdr_col, approve_col = st.columns([6, 1])
                hdr_col.markdown(f"#### {char['name']}")
                approved = approve_col.checkbox(
                    "Approve", value=char["approved"], key=f"approve_{char['name']}"
                )

                with st.expander(
                    f"{'✅' if approved else '⬜'} {char['name']} — "
                    f"{char.get('gender','')} {char.get('age','')} · "
                    f"{char.get('scenes_appears_in','')}",
                    expanded=False,
                ):
                    c1, c2, c3 = st.columns(3)
                    c1.text_input("Age",    value=char["age"],    key=f"age_{char['name']}",    disabled=True)
                    c2.text_input("Gender", value=char["gender"], key=f"gender_{char['name']}", disabled=True)
                    c3.text_input("Build",  value=char["build"],  key=f"build_{char['name']}",  disabled=True)

                    c4, c5, c6 = st.columns(3)
                    c4.text_input("Hair", value=char["hair"], key=f"hair_{char['name']}", disabled=True)
                    c5.text_input("Eyes", value=char["eyes"], key=f"eyes_{char['name']}", disabled=True)
                    c6.text_input("Skin", value=char["skin"], key=f"skin_{char['name']}", disabled=True)

                    st.text_input(
                        "Clothing Style", value=char["clothing_style"],
                        key=f"cloth_{char['name']}", disabled=True
                    )
                    st.text_area(
                        "Visual Description (auto-generated)",
                        value=char["visual_description"],
                        height=68,
                        key=f"vdesc_{char['name']}",
                        disabled=True,
                    )

                    # Editable fields
                    image_url = st.text_input(
                        "🖼️ Image URL",
                        value=char["image_url"],
                        key=f"imgurl_{char['name']}",
                        placeholder="https://… (paste a generated or reference image URL)",
                    )
                    notes = st.text_input(
                        "📝 Notes",
                        value=char["notes"],
                        key=f"notes_{char['name']}",
                        placeholder="casting notes, costume details, references…",
                    )

                st.markdown("</div>", unsafe_allow_html=True)

                updated_chars.append({**char, "approved": approved,
                                       "image_url": image_url, "notes": notes})

            # Write back any edits immediately
            st.session_state.canvas_chars = updated_chars

            approved_count = sum(1 for c in updated_chars if c["approved"])
            st.info(
                f"**{approved_count} / {len(updated_chars)} character(s) approved** "
                f"and will appear in the Character Canvas tab."
            )

            # Canvas preview table
            if st.button("👁️ Preview Character Canvas", use_container_width=True):
                import pandas as _pd
                from generators.sheets_exporter import CANVAS_COLUMNS, build_character_canvas_rows

                overrides = {c["name"]: {"image_url": c["image_url"], "notes": c["notes"]}
                             for c in updated_chars if c["approved"]}
                approved_rows = build_character_canvas_rows(
                    script, st.session_state.char_sheet, approved_overrides=overrides
                )
                approved_rows = [r for r in approved_rows
                                 if r.name in overrides]

                preview_df = _pd.DataFrame(
                    [r.as_list() for r in approved_rows], columns=CANVAS_COLUMNS
                )
                st.dataframe(preview_df, use_container_width=True, height=260)

        elif not st.session_state.canvas_analyzed:
            st.info("Click **Analyze Script for Characters** above to populate the canvas.")

        st.divider()

        # ── Export options ───────────────────────────────────────────────
        col_csv, col_gsheet = st.columns(2, gap="large")

        # ── CSV download (always available) ─────────────────────────────
        with col_csv:
            st.subheader("⬇️ Download CSV")
            st.markdown(
                "No API key needed. Download the CSV and import it into "
                "Google Sheets via **File → Import**."
            )

            from generators.sheets_exporter import SheetsExporter
            exp = SheetsExporter()
            csv_bytes = exp.to_csv_bytes(script)

            safe = script.title.replace(" ", "_")
            st.download_button(
                label="Download CSV",
                data=csv_bytes,
                file_name=f"{safe}_script.csv",
                mime="text/csv",
                type="primary",
                use_container_width=True,
            )

        # ── Google Sheets direct push ────────────────────────────────────
        with col_gsheet:
            st.subheader("☁️ Push to Google Sheets")
            st.markdown(
                "Requires a **Google Service Account** or **OAuth** credentials. "
                "The sheet is created in your Google Drive and shared with you."
            )

            with st.expander("🔑 Google credentials (click to expand)", expanded=False):
                st.markdown(
                    """
**Option A — Service Account (recommended for automation)**
1. Go to [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials
2. Create a Service Account, download the JSON key
3. Share your Google Drive folder with the service account email
4. Paste the JSON content below **or** set `GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/sa.json` in `.env`

**Option B — OAuth (personal use)**
1. Download `credentials.json` from Google Cloud Console (Desktop app OAuth)
2. Set `GOOGLE_OAUTH_CREDENTIALS=/path/to/credentials.json` in `.env`
                    """
                )
                sa_json_input = st.text_area(
                    "Service Account JSON (paste full JSON here)",
                    height=160,
                    placeholder='{"type": "service_account", "project_id": "…", …}',
                    key="sa_json_input",
                )

            sheet_title_input = st.text_input(
                "Sheet title",
                value=f"{script.title} — Script Breakdown",
                key="sheet_title_input",
            )
            share_email = st.text_input(
                "Share with (your email)",
                placeholder="you@gmail.com",
                key="share_email",
            )

            if st.button("🚀 Create Google Sheet", type="primary", use_container_width=True):
                sa_path  = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
                oauth_p  = os.environ.get("GOOGLE_OAUTH_CREDENTIALS")
                sa_json  = sa_json_input.strip() or None

                # Write inline JSON to a temp file if provided
                tmp_sa = None
                if sa_json:
                    import tempfile, json as _json
                    try:
                        _json.loads(sa_json)   # validate
                        tmp = tempfile.NamedTemporaryFile(
                            mode="w", suffix=".json", delete=False
                        )
                        tmp.write(sa_json)
                        tmp.close()
                        tmp_sa = tmp.name
                    except _json.JSONDecodeError as e:
                        st.error(f"Invalid JSON: {e}")
                        st.stop()

                try:
                    # Build approved canvas rows to pass as Tab 2
                    canvas_rows_to_push = None
                    approved_chars = [c for c in st.session_state.canvas_chars if c.get("approved")]
                    if approved_chars:
                        from generators.sheets_exporter import build_character_canvas_rows
                        overrides = {c["name"]: {"image_url": c["image_url"], "notes": c["notes"]}
                                     for c in approved_chars}
                        canvas_rows_to_push = [
                            r for r in build_character_canvas_rows(
                                script, st.session_state.char_sheet,
                                approved_overrides=overrides
                            )
                            if r.name in overrides
                        ]

                    with st.spinner("Creating Google Sheet…"):
                        url = exp.to_google_sheets(
                            script,
                            title=sheet_title_input,
                            share_with=share_email or None,
                            service_account_json=tmp_sa or sa_path,
                            oauth_credentials=oauth_p,
                            canvas_rows=canvas_rows_to_push,
                        )
                    st.session_state.gsheet_url = url
                    tab2_note = (f" + Character Canvas ({len(canvas_rows_to_push)} characters)"
                                 if canvas_rows_to_push else "")
                    st.success(f"Google Sheet created{tab2_note}!")
                    st.markdown(f"**[Open Sheet]({url})**")
                    st.code(url)
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.exception(e)
                finally:
                    if tmp_sa:
                        Path(tmp_sa).unlink(missing_ok=True)

        # ── Generate & Push Scene Images to Sheet ─────────────────────────
        st.divider()
        st.subheader("🎬 Generate & Push Scene Images to Sheet")
        st.caption(
            "Once you have a Google Sheet, this step generates an AI image for "
            "every dialog line and writes the **prompt** (col M) + **=IMAGE() URL** "
            "(col O) directly into the sheet — using Pollinations.ai (free)."
        )

        if not st.session_state.gsheet_url:
            st.info(
                "Create a Google Sheet first using the **Push to Google Sheets** "
                "button above. The sheet URL will appear here automatically."
            )
        else:
            st.success(f"Active sheet: `{st.session_state.gsheet_url}`")

            push_url = st.text_input(
                "Google Sheet URL",
                value=st.session_state.gsheet_url,
                key="push_url_input",
            )

            p_c1, p_c2 = st.columns(2)
            push_model = p_c1.selectbox(
                "Pollinations model",
                ["flux", "flux-realism", "flux-anime", "flux-3d", "turbo"],
                key="push_model",
                help="flux = best quality · turbo = fastest",
            )
            push_seed = p_c2.number_input(
                "Seed (0 = random)", min_value=0, max_value=2**31, value=42, key="push_seed"
            )

            push_scenes_opts = ["All scenes"] + [s.id for s in script.scenes]
            push_scene_sel = st.selectbox(
                "Scenes to generate",
                push_scenes_opts,
                key="push_scene_sel",
            )

            push_style = st.text_input(
                "Extra style tags",
                value=st.session_state.extra_style,
                key="push_extra_style",
                placeholder="e.g. anime, watercolor, cinematic",
            )

            skip_existing = st.checkbox(
                "Skip rows that already have an image URL",
                value=True,
                key="push_skip_existing",
            )

            p_btn1, p_btn2 = st.columns([1, 1])

            # ── Push to Google Sheet (requires credentials) ──────────
            if p_btn1.button(
                "🚀 Generate & Push to Sheet", type="primary", use_container_width=True
            ):
                if st.session_state.anthropic_key:
                    os.environ["ANTHROPIC_API_KEY"] = st.session_state.anthropic_key

                sa_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
                sa_json = st.session_state.get("sa_json_input", "").strip() or None
                tmp_sa = None
                if sa_json:
                    import tempfile, json as _json
                    try:
                        _json.loads(sa_json)
                        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
                        tmp.write(sa_json)
                        tmp.close()
                        tmp_sa = tmp.name
                    except _json.JSONDecodeError:
                        pass

                try:
                    from generators.scene_image_pusher import SceneImagePusher

                    pusher = SceneImagePusher(
                        anthropic_api_key=st.session_state.anthropic_key,
                        pollinations_model=push_model,
                        seed=int(push_seed) if push_seed > 0 else None,
                    )

                    progress_bar = st.progress(0, text="Starting…")
                    status_text = st.empty()

                    def _push_progress(current, total, label):
                        if total > 0:
                            progress_bar.progress(current / total, text=label)
                        status_text.caption(label)

                    selected = (
                        None if push_scene_sel == "All scenes"
                        else [push_scene_sel]
                    )

                    count = pusher.run(
                        spreadsheet_url=push_url,
                        script=script,
                        char_sheet=st.session_state.char_sheet,
                        loc_sheet=st.session_state.loc_sheet,
                        service_account_json=tmp_sa or sa_path,
                        skip_existing=skip_existing,
                        selected_scenes=selected,
                        extra_style=push_style,
                        on_progress=_push_progress,
                    )

                    progress_bar.progress(1.0, text="Done!")
                    status_text.empty()
                    st.success(f"Pushed **{count}** images to the sheet!")
                    st.markdown(f"**[Open Sheet]({push_url})**")

                except Exception as e:
                    st.error(f"Error: {e}")
                    st.exception(e)
                finally:
                    if tmp_sa:
                        Path(tmp_sa).unlink(missing_ok=True)

            # ── Preview locally (no Google credentials needed) ────────
            if p_btn2.button(
                "👁️ Preview Locally (no push)", use_container_width=True
            ):
                if st.session_state.anthropic_key:
                    os.environ["ANTHROPIC_API_KEY"] = st.session_state.anthropic_key

                try:
                    from generators.scene_image_pusher import SceneImagePusher

                    pusher = SceneImagePusher(
                        anthropic_api_key=st.session_state.anthropic_key,
                        pollinations_model=push_model,
                        seed=int(push_seed) if push_seed > 0 else None,
                    )

                    progress_bar = st.progress(0, text="Starting…")

                    def _local_progress(current, total, label):
                        if total > 0:
                            progress_bar.progress(current / total, text=label)

                    selected = (
                        None if push_scene_sel == "All scenes"
                        else [push_scene_sel]
                    )

                    results = pusher.generate_prompts_and_urls(
                        script=script,
                        char_sheet=st.session_state.char_sheet,
                        loc_sheet=st.session_state.loc_sheet,
                        selected_scenes=selected,
                        extra_style=push_style,
                        on_progress=_local_progress,
                    )

                    progress_bar.progress(1.0, text="Done!")
                    st.session_state.scene_image_results = results
                    st.success(f"Generated **{len(results)}** prompts + URLs")

                except Exception as e:
                    st.error(f"Error: {e}")
                    st.exception(e)

        # Show local preview results
        if st.session_state.scene_image_results:
            st.markdown("---")
            st.markdown("##### Local Preview")
            for r in st.session_state.scene_image_results:
                with st.expander(
                    f"🎬 {r['scene_id']} — **{r['character']}**: _{r['text'][:50]}…_"
                    if len(r["text"]) > 50
                    else f"🎬 {r['scene_id']} — **{r['character']}**: _{r['text']}_",
                    expanded=False,
                ):
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        st.image(r["image_url"], caption=r["scene_id"], use_container_width=True)
                    with c2:
                        st.markdown(f"**Prompt:** {r['prompt']}")
                        st.code(r["image_url"], language=None)

        # ── Column legend ────────────────────────────────────────────────
        st.divider()
        st.subheader("Column Reference")
        col_data = {
            "Column": list("ABCDEFGHIJKLMNO"),
            "Name": COLUMNS,
            "Description": [
                "Sequential row number",
                "Scene identifier (scene_01, scene_02 …)",
                "Scene number (1, 2, 3 …)",
                "Location name",
                "Time of day",
                "All characters present in the scene",
                "Line position within the scene",
                "DIALOG / ACTION / SCENE HEADING",
                "Speaker (dialog rows only)",
                "The dialog line or action text",
                "Emotion / tone hint",
                "YES if flagged for image generation",
                "AI-generated image prompt text",
                "Free notes for production use",
                "=IMAGE() formula rendering the scene in the cell",
            ],
        }
        st.dataframe(pd.DataFrame(col_data), use_container_width=True, hide_index=True)

# ===========================================================================
# TAB 5 — Gallery
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
# TAB 6 — Inline Editor
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
