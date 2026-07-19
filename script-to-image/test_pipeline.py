"""
Script-to-Image · Pipeline Test App
=====================================
Standalone test app for the 4-step pipeline:

  Col 1  Dialog text      →  you type it or pick from a loaded script
  Col 2  Image Prompt     →  Claude generates from dialog + context
  Col 3  Image            →  Pollinations.ai (nano banana) renders inline
  Col 4  Video            →  Replicate SVD animates the image

Run:
    cd script-to-image
    streamlit run test_pipeline.py
"""

import io
import os
import sys
import urllib.parse
import csv
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(Path(__file__).parent / ".env")

# ─────────────────────────────────────────────────────────────────────────────
# Page config  (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Pipeline Test · Script-to-Image",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Step cards */
.step-card {
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 10px;
    border: 1px solid #313244;
}
.step-pending  { background:#1e1e2e; border-left:4px solid #45475a; }
.step-running  { background:#1e2030; border-left:4px solid #89b4fa; }
.step-done     { background:#1e2e1e; border-left:4px solid #a6e3a1; }
.step-error    { background:#2e1e1e; border-left:4px solid #f38ba8; }
.step-skipped  { background:#1e1e2e; border-left:4px solid #6c7086; opacity:0.7; }

.step-num {
    font-size:0.7em; font-weight:bold; letter-spacing:2px;
    text-transform:uppercase; margin-bottom:2px;
}
.step-num-pending  { color:#6c7086; }
.step-num-running  { color:#89b4fa; }
.step-num-done     { color:#a6e3a1; }
.step-num-error    { color:#f38ba8; }

/* History row */
.hist-row {
    display:flex; gap:10px; align-items:flex-start;
    padding:8px 0; border-bottom:1px solid #313244;
}
.hist-badge {
    font-size:0.72em; padding:2px 8px; border-radius:12px;
    white-space:nowrap; font-weight:600;
}
.badge-done  { background:#1e2e1e; color:#a6e3a1; border:1px solid #a6e3a1; }
.badge-error { background:#2e1e1e; color:#f38ba8; border:1px solid #f38ba8; }

/* Pipeline arrow connector */
.arrow { text-align:center; font-size:1.4em; color:#585b70; margin:2px 0; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Session state defaults
# ─────────────────────────────────────────────────────────────────────────────
_DEFAULTS = {
    "history": [],           # list of result dicts
    "char_sheet": None,
    "loc_sheet": None,
    "script": None,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

EXAMPLES_DIR = Path(__file__).parent / "examples"

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🎬 Pipeline Test")
    st.caption("4-step scene generator")
    st.divider()

    st.subheader("🔑 API Keys")
    anthropic_key = st.text_input(
        "Anthropic API key",
        type="password",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        placeholder="sk-ant-…  (required for Step 2)",
    )
    replicate_token = st.text_input(
        "Replicate token",
        type="password",
        value=os.environ.get("REPLICATE_API_TOKEN", ""),
        placeholder="r8_…  (optional, for Step 4 video)",
    )

    st.divider()
    st.subheader("🖼️ Image — Pollinations.ai")
    poll_model = st.selectbox(
        "Model",
        ["flux", "flux-realism", "flux-anime", "flux-3d", "turbo"],
        help="flux = best quality · turbo = fastest",
    )
    col_w, col_h = st.columns(2)
    img_w = col_w.selectbox("Width",  [512, 768, 1024], index=2)
    img_h = col_h.selectbox("Height", [288, 512, 576],  index=2)
    seed = st.number_input("Seed  (0 = random)", 0, 2**31, 42)

    st.divider()
    st.subheader("🎥 Video — Replicate SVD")
    use_video = st.toggle(
        "Enable video generation",
        value=bool(replicate_token),
        help="Requires Replicate token. ~$0.01/run.",
    )
    fps    = st.slider("FPS",           4, 12, 8)
    motion = st.slider("Motion amount", 1, 255, 100)

    st.divider()
    # Status indicators
    st.markdown(
        f"{'✅' if anthropic_key else '❌'} Claude (prompt gen)  \n"
        f"✅ Pollinations.ai (image — free)  \n"
        f"{'✅' if replicate_token and use_video else '⚠️'} "
        f"Replicate SVD {'(video on)' if use_video and replicate_token else '(mock mode)'}"
    )

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.title("🎬 Script-to-Image · Pipeline Test")
st.markdown(
    "Test the full **Dialog → Prompt → Image → Video** pipeline. "
    "Type a single line, or load a script and pick a scene."
)

# ─────────────────────────────────────────────────────────────────────────────
# Two-column layout: input + pipeline  |  history
# ─────────────────────────────────────────────────────────────────────────────
left, right = st.columns([3, 2], gap="large")

# ═══════════════════════════════════════════════════════════════════════════
# LEFT — Input + Pipeline
# ═══════════════════════════════════════════════════════════════════════════
with left:
    mode = st.radio(
        "Input mode",
        ["✏️  Type manually", "📜  From loaded script"],
        horizontal=True,
        label_visibility="collapsed",
    )

    # ── Mode A: Manual input ─────────────────────────────────────────────
    if "Type manually" in mode:
        with st.form("manual_form"):
            dialog = st.text_area(
                "Dialog line",
                placeholder="End of the line, Elena. Hand over the drive.",
                height=80,
            )
            fc1, fc2 = st.columns(2)
            character = fc1.text_input(
                "Character",
                placeholder="Marcus — detective, trench coat",
            )
            location = fc2.text_input(
                "Location",
                placeholder="rain-slicked neon alley, midnight",
            )
            emotion = st.text_input(
                "Emotion / tone",
                placeholder="threatening, tired  (optional)",
            )
            extra_style = st.text_input(
                "Extra style tags",
                placeholder="cinematic, anime, oil painting  (optional)",
            )
            submitted = st.form_submit_button(
                "▶  Run Pipeline", type="primary", use_container_width=True
            )

        if submitted:
            if not dialog.strip():
                st.warning("Enter a dialog line first.")
                submitted = False

    # ── Mode B: From script ──────────────────────────────────────────────
    else:
        sc1, sc2 = st.columns(2)
        load_chars = sc1.button("Load example characters", use_container_width=True)
        load_locs  = sc1.button("Load example locations",  use_container_width=True)
        load_scr   = sc2.button("Load example script",     use_container_width=True)

        if load_chars:
            from models.character import CharacterSheet
            st.session_state.char_sheet = CharacterSheet.from_json_file(
                str(EXAMPLES_DIR / "characters.json"))
        if load_locs:
            from models.location import LocationSheet
            st.session_state.loc_sheet = LocationSheet.from_json_file(
                str(EXAMPLES_DIR / "locations.json"))
        if load_scr:
            from models.script import Script
            st.session_state.script = Script.from_json_file(
                str(EXAMPLES_DIR / "sample_script.json"))

        assets_ok = (st.session_state.script is not None
                     and st.session_state.char_sheet is not None
                     and st.session_state.loc_sheet is not None)

        if not assets_ok:
            st.info("Load characters, locations, and a script using the buttons above.")
            submitted = False
        else:
            scr = st.session_state.script
            scene_options = {s.id: s for s in scr.scenes}
            chosen_scene_id = st.selectbox("Scene", list(scene_options.keys()))
            chosen_scene = scene_options[chosen_scene_id]

            dialog_lines = [
                (i, l) for i, l in enumerate(chosen_scene.lines)
                if l.type == "dialog"
            ]
            if not dialog_lines:
                st.warning("No dialog lines in this scene.")
                submitted = False
            else:
                line_labels = [
                    f"{l.character}: {l.text[:60]}{'…' if len(l.text)>60 else ''}"
                    for _, l in dialog_lines
                ]
                chosen_idx = st.selectbox(
                    "Dialog line", range(len(dialog_lines)),
                    format_func=lambda i: line_labels[i],
                )
                _, chosen_line = dialog_lines[chosen_idx]

                dialog     = chosen_line.text
                character  = chosen_line.character or ""
                emotion    = chosen_line.emotion or ""
                extra_style = ""

                loc_obj = st.session_state.loc_sheet.get(chosen_scene.location)
                location = loc_obj.to_prompt_fragment() if loc_obj else chosen_scene.location

                char_obj = st.session_state.char_sheet.get(character)
                if char_obj:
                    character = f"{character} — {char_obj.to_prompt_fragment()}"

                st.markdown(
                    f"**Selected:** `{chosen_scene_id}` · "
                    f"**{chosen_line.character}**: _{chosen_line.text}_"
                )
                submitted = st.button(
                    "▶  Run Pipeline", type="primary", use_container_width=True
                )

    # ─────────────────────────────────────────────────────────────────────
    # Pipeline execution
    # ─────────────────────────────────────────────────────────────────────
    if submitted:
        if not anthropic_key:
            st.error("Add your Anthropic API key in the sidebar to generate prompts.")
            st.stop()

        os.environ["ANTHROPIC_API_KEY"] = anthropic_key
        if replicate_token:
            os.environ["REPLICATE_API_TOKEN"] = replicate_token

        result = {
            "dialog":    f"{character.split(' — ')[0] if ' — ' in character else character}: {dialog}",
            "prompt":    None,
            "image_url": None,
            "video_url": None,
            "error":     None,
        }

        st.divider()
        st.subheader("Pipeline")

        # ── Step 1 ──────────────────────────────────────────────────────
        st.markdown(
            '<div class="step-card step-done">'
            '<div class="step-num step-num-done">Step 1 · Dialog</div>'
            f'<strong>{character.split(" — ")[0] if " — " in character else character}</strong>: '
            f'{dialog}'
            f'{"<br><small><em>Emotion: " + emotion + "</em></small>" if emotion else ""}'
            f'{"<br><small><em>Location: " + location[:80] + "</em></small>" if location else ""}'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="arrow">↓</div>', unsafe_allow_html=True)

        # ── Step 2: Prompt ──────────────────────────────────────────────
        prompt_result = None
        with st.status("Step 2 · Generating prompt (Claude)…", expanded=True) as s2:
            try:
                import anthropic as _ant
                _system = (
                    "You are a cinematic storyboard artist and Midjourney/Stable Diffusion "
                    "prompt engineer. Given a screenplay dialog line with character and "
                    "location context, write ONE concise image generation prompt. "
                    "Output ONLY the prompt — no labels, no explanation. "
                    "Max 100 words. End with: highly detailed, cinematic lighting, 8k."
                )
                _user = (
                    f"CHARACTER: {character or 'unknown'}\n"
                    f"LOCATION:  {location or 'unspecified'}\n"
                    f"EMOTION:   {emotion or 'infer from dialog'}\n"
                    f"DIALOG:    \"{dialog}\"\n"
                    + (f"STYLE:     {extra_style}\n" if extra_style else "")
                    + "\nGenerate the image prompt."
                )
                client = _ant.Anthropic(api_key=anthropic_key)
                resp = client.messages.create(
                    model="claude-sonnet-4-6", max_tokens=200,
                    system=_system,
                    messages=[{"role": "user", "content": _user}],
                )
                prompt_result = resp.content[0].text.strip()
                result["prompt"] = prompt_result
                s2.update(label="Step 2 · Prompt ready ✅", state="complete")
            except Exception as e:
                result["error"] = str(e)
                s2.update(label=f"Step 2 · Error: {e}", state="error")
                st.error(str(e))
                st.session_state.history.insert(0, result)
                st.stop()

        st.markdown(
            '<div class="step-card step-done">'
            '<div class="step-num step-num-done">Step 2 · Image Prompt</div>'
            f'{prompt_result}'
            '</div>',
            unsafe_allow_html=True,
        )

        # Editable prompt before image generation
        edited_prompt = st.text_area(
            "✏️ Edit prompt before generating image (optional)",
            value=prompt_result,
            height=68,
            key="edited_prompt",
        )
        if edited_prompt.strip():
            prompt_result = edited_prompt.strip()

        st.markdown('<div class="arrow">↓</div>', unsafe_allow_html=True)

        # ── Step 3: Image ───────────────────────────────────────────────
        image_url = None
        with st.status("Step 3 · Generating image (Pollinations.ai)…", expanded=True) as s3:
            try:
                encoded = urllib.parse.quote(prompt_result, safe="")
                params = (
                    f"?width={img_w}&height={img_h}"
                    f"&model={poll_model}&nologo=true&enhance=false"
                )
                if seed > 0:
                    params += f"&seed={seed}"
                image_url = f"https://image.pollinations.ai/prompt/{encoded}{params}"

                import requests as _req
                r = _req.get(image_url, timeout=90)
                r.raise_for_status()
                result["image_url"] = image_url
                s3.update(label="Step 3 · Image ready ✅", state="complete")
            except Exception as e:
                result["error"] = str(e)
                s3.update(label=f"Step 3 · Error: {e}", state="error")
                st.error(str(e))
                st.session_state.history.insert(0, result)
                st.stop()

        st.image(image_url, use_container_width=True)
        st.code(image_url, language=None)
        st.markdown('<div class="arrow">↓</div>', unsafe_allow_html=True)

        # ── Step 4: Video ───────────────────────────────────────────────
        video_url = None
        real_video = use_video and bool(replicate_token)

        with st.status(
            "Step 4 · Generating video (Replicate SVD)…" if real_video
            else "Step 4 · Video  (mock — no Replicate token)",
            expanded=True,
        ) as s4:
            try:
                from generators.video_generator import VideoGenerator
                vg = VideoGenerator(
                    replicate_token=replicate_token,
                    backend="replicate" if real_video else "mock",
                    fps=fps,
                    motion_bucket_id=motion,
                )
                video_url = vg.generate(image_url)
                result["video_url"] = video_url
                s4.update(
                    label="Step 4 · Video ready ✅" if real_video
                    else "Step 4 · Mock ✅ (add Replicate token for real video)",
                    state="complete",
                )
            except Exception as e:
                s4.update(label=f"Step 4 · Error: {e}", state="error")
                video_url = image_url  # graceful fallback

        if video_url and video_url.endswith(".mp4"):
            st.video(video_url)
        else:
            st.image(video_url, caption="Mock — shows image (no Replicate token)", use_container_width=True)
        st.code(video_url or "", language=None)

        # Save to history
        st.session_state.history.insert(0, result)
        st.success("Pipeline complete! Results saved to History →")

# ═══════════════════════════════════════════════════════════════════════════
# RIGHT — History + Google Sheet summary
# ═══════════════════════════════════════════════════════════════════════════
with right:
    st.subheader("📋 History")

    if not st.session_state.history:
        st.caption("Run the pipeline to see results here.")
    else:
        # CSV download
        def _to_csv(rows: list) -> bytes:
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=["dialog", "prompt", "image_url", "video_url", "error"])
            w.writeheader()
            w.writerows(rows)
            return buf.getvalue().encode()

        st.download_button(
            "⬇️ Download history CSV",
            data=_to_csv(st.session_state.history),
            file_name="pipeline_history.csv",
            mime="text/csv",
            use_container_width=True,
        )

        if st.button("🗑️ Clear history", use_container_width=True):
            st.session_state.history = []
            st.rerun()

        st.divider()

        # Show each history entry
        for i, entry in enumerate(st.session_state.history):
            badge = (
                '<span class="hist-badge badge-error">error</span>'
                if entry.get("error")
                else '<span class="hist-badge badge-done">done</span>'
            )
            with st.expander(
                f"{badge}  {entry['dialog'][:55]}{'…' if len(entry['dialog'])>55 else ''}",
                expanded=(i == 0),
            ):
                # Step 2 — Prompt
                if entry.get("prompt"):
                    st.markdown("**2 · Prompt**")
                    st.caption(entry["prompt"])

                # Step 3 — Image
                if entry.get("image_url"):
                    st.markdown("**3 · Image**")
                    st.image(entry["image_url"], use_container_width=True)
                    st.code(entry["image_url"], language=None)

                # Step 4 — Video
                if entry.get("video_url") and entry["video_url"] != entry.get("image_url"):
                    st.markdown("**4 · Video**")
                    if entry["video_url"].endswith(".mp4"):
                        st.video(entry["video_url"])
                    st.code(entry["video_url"], language=None)

                if entry.get("error"):
                    st.error(entry["error"])

        st.divider()

        # Google Sheet paste helper — last result
        last = st.session_state.history[0]
        if last.get("prompt"):
            st.markdown("#### Google Sheet columns (last run)")
            st.markdown("Copy these into your sheet row:")

            col_data = {
                "Column": ["J — Dialog", "M — Prompt", "O — Image URL", "P — Video URL"],
                "Value":  [
                    last["dialog"],
                    last.get("prompt", ""),
                    last.get("image_url", ""),
                    last.get("video_url", ""),
                ],
            }
            import pandas as pd
            st.dataframe(
                pd.DataFrame(col_data),
                use_container_width=True,
                hide_index=True,
            )

            # One-click Google Sheet formula for image column
            if last.get("image_url"):
                formula = f'=IMAGE("{last["image_url"]}")'
                st.markdown("**Image formula for col O:**")
                st.code(formula, language=None)
