"""
Script-to-Image Generator — GUI App
=====================================
Polished Streamlit GUI that accepts a .docx Word script file
and produces a Google Sheets Canvas (Tab 1: Script, Tab 2: Characters).

Run locally:
    streamlit run gui_app.py

Or via the Windows executable built with PyInstaller.
"""

import io
import json
import os
import sys
import time
import tempfile
from pathlib import Path

import streamlit as st

# ── path fix for PyInstaller bundle ──────────────────────────────────────────
_BASE = getattr(sys, "_MEIPASS", Path(__file__).parent)
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

# ── page config (MUST be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Script → Google Sheets Canvas",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Main background */
.stApp { background: #0f0f1a; color: #e0e0f0; }

/* Sidebar */
[data-testid="stSidebar"] { background: #1a1a2e; border-right: 1px solid #2a2a4a; }

/* Cards */
.card {
    background: #1a1a2e;
    border: 1px solid #2a2a4a;
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1rem;
}

/* Step badge */
.step-badge {
    display: inline-block;
    background: linear-gradient(135deg, #6c63ff, #3ecfcf);
    color: white;
    border-radius: 50%;
    width: 28px; height: 28px;
    text-align: center;
    line-height: 28px;
    font-weight: 700;
    font-size: 14px;
    margin-right: 8px;
}

/* Progress bar accent */
.stProgress > div > div { background: linear-gradient(90deg, #6c63ff, #3ecfcf); }

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, #6c63ff, #3ecfcf);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    padding: 0.5rem 1.4rem;
    transition: opacity 0.2s;
}
.stButton > button:hover { opacity: 0.85; }

/* Success / error banners */
.stSuccess { background: #0d2b1f; border-left: 4px solid #3ecfcf; }
.stError   { background: #2b0d0d; border-left: 4px solid #ff6c6c; }

/* Tab strip */
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] {
    background: #1a1a2e; border-radius: 8px 8px 0 0;
    border: 1px solid #2a2a4a; border-bottom: none;
    color: #a0a0c0; font-weight: 600;
}
.stTabs [aria-selected="true"] {
    background: #6c63ff !important; color: white !important;
}

/* Metric boxes */
[data-testid="stMetric"] {
    background: #1a1a2e; border: 1px solid #2a2a4a;
    border-radius: 10px; padding: 0.8rem 1rem;
}

/* File uploader */
[data-testid="stFileUploader"] {
    background: #1a1a2e; border: 2px dashed #3c3c6e;
    border-radius: 12px; padding: 1rem;
}
</style>
""", unsafe_allow_html=True)


# ── session state defaults ────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "script": None,
        "parsed_title": "",
        "characters": [],
        "locations": [],
        "char_sheet": None,
        "loc_sheet": None,
        "canvas_rows": None,
        "approved_chars": {},
        "sheets_url": "",
        "step": 0,          # 0=idle, 1=parsed, 2=reviewed, 3=done
        "log": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


def _log(msg: str, kind: str = "info"):
    icon = {"info": "ℹ️", "ok": "✅", "warn": "⚠️", "err": "❌"}.get(kind, "•")
    ts = time.strftime("%H:%M:%S")
    st.session_state.log.append(f"`{ts}` {icon} {msg}")


# ── helpers ───────────────────────────────────────────────────────────────────
def _load_generators():
    """Lazy-import heavy generators so the app starts fast."""
    from generators.sheets_exporter import SheetsExporter
    from generators.scene_image_pusher import SceneImagePusher
    return SheetsExporter, SceneImagePusher


def _parse_docx(uploaded_file) -> "Script":
    from parsers.docx_parser import DocxParser
    data = uploaded_file.read()
    parser = DocxParser()
    return parser.parse_bytes(data, uploaded_file.name)


def _build_char_sheet_from_script(script):
    """Extract unique characters from script and build a lightweight CharacterSheet."""
    from models.character import Character, CharacterSheet
    chars = {}
    for scene in script.scenes:
        for line in scene.lines:
            if line.character and line.character not in chars:
                chars[line.character] = Character(
                    name=line.character,
                    age="unknown",
                    gender="unknown",
                    ethnicity="unknown",
                    build="average",
                    hair="unknown",
                    eyes="unknown",
                    skin="unknown",
                    clothing_style="contextual",
                    distinguishing_features="",
                    personality="",
                    art_style_tags="cinematic, photorealistic",
                    visual_description=f"{line.character} from the script",
                )
    return CharacterSheet(characters=list(chars.values()))


def _build_loc_sheet_from_script(script):
    """Extract unique locations and build a lightweight LocationSheet."""
    from models.location import Location, LocationSheet
    seen = {}
    for scene in script.scenes:
        key = scene.location
        if key and key not in seen:
            seen[key] = Location(
                name=key,
                description=f"{key} — {scene.time_of_day}",
                lighting=scene.time_of_day,
                mood="neutral",
                art_style_tags="cinematic, detailed",
            )
    return LocationSheet(locations=list(seen.values()))


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎬 Script → Canvas")
    st.markdown("---")

    # API Keys
    st.markdown("### 🔑 API Keys")
    anthropic_key = st.text_input(
        "Anthropic API Key", type="password",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        help="Required to generate image prompts from dialog",
    )
    gsheets_creds = st.text_area(
        "Google Service Account JSON",
        value=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", ""),
        height=80,
        help="Paste the full service-account JSON to write to Google Sheets",
    )
    gsheets_url = st.text_input(
        "Google Sheets URL (optional)",
        value=st.session_state.sheets_url,
        help="Leave blank to create a new spreadsheet",
    )
    st.session_state.sheets_url = gsheets_url

    if anthropic_key:
        os.environ["ANTHROPIC_API_KEY"] = anthropic_key
    if gsheets_creds:
        os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = gsheets_creds

    st.markdown("---")

    # Pipeline toggles
    st.markdown("### ⚙️ Pipeline Steps")
    do_prompts = st.toggle("Generate AI Prompts (col M)", value=True)
    do_images  = st.toggle("Generate Images / Pollinations (col O)", value=True)
    do_videos  = st.toggle("Generate Videos / Replicate (col P)", value=False)
    do_canvas  = st.toggle("Character Canvas (Tab 2)", value=True)

    st.markdown("---")
    st.markdown("### 📋 Activity Log")
    if st.button("Clear Log"):
        st.session_state.log = []
    log_box = st.empty()


def _render_log():
    if st.session_state.log:
        log_box.markdown("\n\n".join(st.session_state.log[-20:]))


# ── MAIN AREA ─────────────────────────────────────────────────────────────────
st.markdown("# 🎬 Script → Google Sheets Canvas")
st.markdown(
    "Upload a Word `.docx` screenplay → auto-extract characters & locations → "
    "generate AI image prompts → publish to Google Sheets."
)

tab_upload, tab_review, tab_run, tab_result = st.tabs([
    "📄  1 · Upload Script",
    "👥  2 · Review Characters",
    "🚀  3 · Run Pipeline",
    "📊  4 · Result",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — UPLOAD & PARSE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_upload:
    st.markdown("### Upload your screenplay (.docx)")

    col_upload, col_info = st.columns([1, 1], gap="large")

    with col_upload:
        uploaded = st.file_uploader(
            "Drag & drop or click to browse",
            type=["docx"],
            label_visibility="collapsed",
        )

        if uploaded:
            with st.spinner("Parsing screenplay…"):
                try:
                    script = _parse_docx(uploaded)
                    st.session_state.script = script
                    st.session_state.parsed_title = script.title or Path(uploaded.name).stem
                    st.session_state.char_sheet = _build_char_sheet_from_script(script)
                    st.session_state.loc_sheet  = _build_loc_sheet_from_script(script)
                    st.session_state.step = 1

                    # Pre-fill approved_chars
                    st.session_state.approved_chars = {
                        c.name: True
                        for c in st.session_state.char_sheet.characters
                    }
                    _log(f"Parsed '{script.title}': {len(script.scenes)} scenes", "ok")
                except Exception as exc:
                    st.error(f"Could not parse file: {exc}")
                    _log(str(exc), "err")

        if st.session_state.script:
            st.success(f"✅ **{st.session_state.parsed_title}** loaded")

    with col_info:
        if st.session_state.script:
            script = st.session_state.script
            total_lines = sum(len(s.lines) for s in script.scenes)
            chars = st.session_state.char_sheet.characters
            locs  = st.session_state.loc_sheet.locations

            c1, c2, c3 = st.columns(3)
            c1.metric("Scenes", len(script.scenes))
            c2.metric("Dialog Lines", total_lines)
            c3.metric("Characters", len(chars))

            st.markdown("#### Scene Overview")
            rows = []
            for scene in script.scenes[:20]:
                rows.append({
                    "Scene": scene.scene_id,
                    "Location": scene.location,
                    "Time": scene.time_of_day,
                    "Lines": len(scene.lines),
                })
            import pandas as pd
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            if len(script.scenes) > 20:
                st.caption(f"… and {len(script.scenes)-20} more scenes")
        else:
            st.markdown("""
<div class="card">
<b>Supported formats</b><br><br>
• Standard screenplay format (INT./EXT. headings)<br>
• ALL-CAPS character names before dialog<br>
• Table-based script layouts<br>
• Fountain-style plain text inside .docx
</div>
""", unsafe_allow_html=True)

    _render_log()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — REVIEW CHARACTERS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_review:
    if not st.session_state.script:
        st.info("Upload a script in Tab 1 first.")
    else:
        st.markdown("### Review extracted characters")
        st.caption(
            "Edit descriptions and toggle approval. Only approved characters "
            "are added to the Character Canvas (Tab 2 in Google Sheets)."
        )

        char_sheet = st.session_state.char_sheet
        updated_chars = []

        for i, char in enumerate(char_sheet.characters):
            with st.expander(f"👤  {char.name}", expanded=True):
                col_a, col_b, col_c = st.columns([2, 2, 1])
                with col_a:
                    char.age    = st.text_input("Age",    value=char.age,    key=f"age_{i}")
                    char.gender = st.text_input("Gender", value=char.gender, key=f"gen_{i}")
                    char.build  = st.text_input("Build",  value=char.build,  key=f"bld_{i}")
                with col_b:
                    char.hair  = st.text_input("Hair",  value=char.hair,  key=f"hair_{i}")
                    char.eyes  = st.text_input("Eyes",  value=char.eyes,  key=f"eyes_{i}")
                    char.skin  = st.text_input("Skin",  value=char.skin,  key=f"skin_{i}")
                with col_c:
                    approved = st.checkbox(
                        "Approve",
                        value=st.session_state.approved_chars.get(char.name, True),
                        key=f"appr_{i}",
                    )
                    st.session_state.approved_chars[char.name] = approved
                    img_url = st.text_input(
                        "Image URL", value="", key=f"img_{i}",
                        placeholder="https://…",
                        help="Paste a character reference image URL (optional)",
                    )
                    char.image_url = img_url  # store on object

                char.visual_description = st.text_area(
                    "Visual Description",
                    value=char.visual_description,
                    key=f"vdesc_{i}",
                    height=68,
                )
                char.art_style_tags = st.text_input(
                    "Art Style Tags",
                    value=char.art_style_tags,
                    key=f"ast_{i}",
                )
                updated_chars.append(char)

        char_sheet.characters = updated_chars
        st.session_state.char_sheet = char_sheet

        approved_count = sum(1 for v in st.session_state.approved_chars.values() if v)
        st.markdown(f"**{approved_count} / {len(char_sheet.characters)} characters approved**")

        if st.button("✅  Confirm Characters & Continue →"):
            st.session_state.step = max(st.session_state.step, 2)
            _log(f"Characters confirmed ({approved_count} approved)", "ok")
            st.success("Characters confirmed! Go to Tab 3 to run the pipeline.")

    _render_log()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — RUN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_run:
    if not st.session_state.script:
        st.info("Upload a script in Tab 1 first.")
    elif st.session_state.step < 1:
        st.info("Finish reviewing characters in Tab 2 first.")
    else:
        st.markdown("### Run the pipeline")

        # Summary card
        script = st.session_state.script
        total_lines = sum(len(s.lines) for s in script.scenes)
        st.markdown(f"""
<div class="card">
<b>📋 {st.session_state.parsed_title}</b> &nbsp;·&nbsp;
{len(script.scenes)} scenes &nbsp;·&nbsp; {total_lines} dialog lines &nbsp;·&nbsp;
{len(st.session_state.char_sheet.characters)} characters
</div>
""", unsafe_allow_html=True)

        # Steps preview
        steps_col, run_col = st.columns([1, 1], gap="large")

        with steps_col:
            st.markdown("#### Steps to execute")

            def _step_row(num, label, enabled, desc):
                icon = "🟢" if enabled else "⬜"
                st.markdown(
                    f'<span class="step-badge">{num}</span> {icon} **{label}**  \n'
                    f'<small style="color:#888">{desc}</small>',
                    unsafe_allow_html=True,
                )

            _step_row(1, "Export to Google Sheets",    True,
                      "Tab 1: one row per dialog line (cols A–J)")
            _step_row(2, "Generate AI Prompts",        do_prompts,
                      "Claude reads dialog → writes prompt to col M")
            _step_row(3, "Generate Images (Pollinations)", do_images,
                      "Prompt → free image URL → col O as =IMAGE()")
            _step_row(4, "Generate Videos (Replicate)",   do_videos,
                      "Image → SVD video URL → col P")
            _step_row(5, "Character Canvas",           do_canvas,
                      "Tab 2: profiles for all approved characters")

        with run_col:
            st.markdown("#### Launch")
            run_btn = st.button("🚀  Run Pipeline", use_container_width=True,
                                disabled=(st.session_state.step >= 3))

        if run_btn or st.session_state.get("_run_triggered"):
            st.session_state["_run_triggered"] = False

            # Validate keys
            if not os.getenv("ANTHROPIC_API_KEY") and do_prompts:
                st.error("Set your **Anthropic API Key** in the sidebar first.")
                _log("Missing Anthropic API key", "err")
                st.stop()
            if not os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"):
                st.error("Paste your **Google Service Account JSON** in the sidebar first.")
                _log("Missing Google credentials", "err")
                st.stop()

            progress = st.progress(0, text="Starting…")
            status   = st.empty()

            try:
                SheetsExporter, SceneImagePusher = _load_generators()

                # ── STEP 1: Export script to Google Sheets ──────────────────
                status.info("📤 Exporting script to Google Sheets…")
                progress.progress(10, "Exporting script…")

                exporter = SheetsExporter()
                canvas_rows = None
                if do_canvas:
                    from generators.sheets_exporter import build_character_canvas_rows
                    canvas_rows = build_character_canvas_rows(
                        script,
                        st.session_state.char_sheet,
                        st.session_state.approved_chars,
                    )

                spreadsheet_url = st.session_state.sheets_url or None
                result_url = exporter.to_google_sheets(
                    script,
                    canvas_rows=canvas_rows,
                    spreadsheet_url=spreadsheet_url,
                )
                st.session_state.sheets_url = result_url
                _log(f"Google Sheet created: {result_url}", "ok")
                progress.progress(30, "Script exported ✓")

                # ── STEP 2–4: Prompts / Images / Videos ─────────────────────
                if do_prompts or do_images or do_videos:
                    status.info("🤖 Running image pipeline…")
                    pusher = SceneImagePusher()
                    counts = pusher.run(
                        spreadsheet_url=result_url,
                        script=script,
                        char_sheet=st.session_state.char_sheet,
                        loc_sheet=st.session_state.loc_sheet,
                        push_prompts=do_prompts,
                        push_images=do_images,
                        push_videos=do_videos,
                        skip_existing=True,
                    )
                    _log(
                        f"Prompts: {counts.get('prompts',0)} | "
                        f"Images: {counts.get('images',0)} | "
                        f"Videos: {counts.get('videos',0)}", "ok"
                    )
                    progress.progress(90, "Pipeline complete ✓")

                progress.progress(100, "Done! ✅")
                status.success("Pipeline complete!")
                st.session_state.step = 3
                _log("Pipeline finished", "ok")

            except Exception as exc:
                progress.progress(0)
                status.error(f"Pipeline error: {exc}")
                _log(str(exc), "err")
                import traceback
                st.expander("Error details").code(traceback.format_exc())

    _render_log()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — RESULT
# ═══════════════════════════════════════════════════════════════════════════════
with tab_result:
    if st.session_state.step >= 3 and st.session_state.sheets_url:
        url = st.session_state.sheets_url
        st.success("### 🎉 Your Google Sheet is ready!")
        st.markdown(f"[📊 Open Google Sheet]({url})", unsafe_allow_html=False)

        st.markdown("#### What's inside")
        st.markdown("""
| Tab | Contents |
|-----|----------|
| **Tab 1 — Script** | One row per dialog line · cols A–J = context · col M = AI prompt · col O = image · col P = video |
| **Tab 2 — Character Canvas** | One row per approved character · full profile + reference image |
""")
        st.markdown("#### Sheet URL")
        st.code(url)

        if st.button("🔄 Start Over"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            _init_state()
            st.rerun()

    elif st.session_state.step > 0:
        st.info("Run the pipeline in Tab 3 to see results here.")
    else:
        st.info("Upload a script and run the pipeline to see results here.")

    _render_log()
