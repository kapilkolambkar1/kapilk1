"""
4-Step Scene Pipeline — Test App
=================================
Tests the full dialog → prompt → image → video pipeline for a single line.

Run:
    cd script-to-image
    streamlit run test_pipeline.py

Steps tested:
  1  Dialog text       (you type it)
  2  Image Prompt      (Claude generates from dialog + character + location)
  3  Image URL         (Pollinations.ai — free, no API key)
  4  Video URL         (Replicate SVD — needs REPLICATE_API_TOKEN)
"""

import os
import sys
import time
import urllib.parse
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(Path(__file__).parent / ".env")

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Pipeline Test",
    page_icon="🎬",
    layout="centered",
)

st.markdown(
    """
    <style>
    .step-box {
        border-left: 4px solid #89b4fa;
        background: #1e1e2e;
        border-radius: 0 10px 10px 0;
        padding: 14px 18px;
        margin: 10px 0 18px 0;
    }
    .step-label {
        font-size: 0.78em;
        color: #89b4fa;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 4px;
    }
    .step-done  { border-left-color: #a6e3a1; }
    .step-error { border-left-color: #f38ba8; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar — API keys ───────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔑 API Keys")
    anthropic_key = st.text_input(
        "Anthropic (Claude)", type="password",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        placeholder="sk-ant-…",
    )
    replicate_token = st.text_input(
        "Replicate (video)", type="password",
        value=os.environ.get("REPLICATE_API_TOKEN", ""),
        placeholder="r8_… (optional)",
    )

    st.divider()
    st.subheader("⚙️ Image settings")
    poll_model = st.selectbox(
        "Pollinations model",
        ["flux", "flux-realism", "flux-anime", "flux-3d", "turbo"],
    )
    img_width  = st.select_slider("Width",  options=[512, 768, 1024], value=1024)
    img_height = st.select_slider("Height", options=[288, 512, 576],  value=576)
    seed = st.number_input("Seed (0 = random)", 0, 2**31, 42)

    st.divider()
    st.subheader("🎥 Video settings")
    video_backend = st.radio(
        "Video backend",
        ["mock (no credits)", "replicate (SVD)"],
        index=0 if not replicate_token else 1,
    )
    fps = st.slider("FPS", 4, 12, 8)
    motion = st.slider("Motion amount", 1, 255, 100)

# ── Main area ────────────────────────────────────────────────────────────────
st.title("🎬 Scene Pipeline Test")
st.caption("Dialog → Prompt → Image → Video  ·  step by step")

# ── Input form ───────────────────────────────────────────────────────────────
with st.form("pipeline_form"):
    dialog = st.text_area(
        "1 · Dialog line",
        placeholder="e.g.  End of the line, Elena. Hand over the drive.",
        height=80,
    )
    c1, c2 = st.columns(2)
    character = c1.text_input(
        "Character speaking",
        placeholder="e.g.  Marcus — broad detective, trench coat",
    )
    location = c2.text_input(
        "Location",
        placeholder="e.g.  rain-slicked neon alley, midnight, noir mood",
    )
    emotion = st.text_input(
        "Emotion / tone  (optional)",
        placeholder="e.g.  threatening, tired",
    )
    extra_style = st.text_input(
        "Extra style tags  (optional)",
        placeholder="e.g.  cinematic, oil painting, anime",
    )

    run_btn = st.form_submit_button("▶ Run Pipeline", type="primary", use_container_width=True)

# ── Pipeline execution ───────────────────────────────────────────────────────
if run_btn:
    if not dialog.strip():
        st.warning("Enter a dialog line first.")
        st.stop()
    if not anthropic_key:
        st.error("Anthropic API key is required for step 2 (prompt generation).")
        st.stop()

    os.environ["ANTHROPIC_API_KEY"] = anthropic_key
    if replicate_token:
        os.environ["REPLICATE_API_TOKEN"] = replicate_token

    # ── STEP 1: Dialog ───────────────────────────────────────────────────
    st.markdown(
        '<div class="step-box step-done">'
        '<div class="step-label">Step 1 — Dialog</div>'
        f'<strong>{character or "Character"}</strong>: {dialog}'
        f'{"<br><em>Emotion: " + emotion + "</em>" if emotion else ""}'
        f'{"<br><em>Location: " + location + "</em>" if location else ""}'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── STEP 2: Generate prompt via Claude ───────────────────────────────
    prompt_result = None
    with st.status("Step 2 — Generating image prompt (Claude)…", expanded=True) as status2:
        try:
            import anthropic as _anthropic

            _system = (
                "You are a cinematic storyboard artist and image prompt engineer. "
                "Given a screenplay dialog line with character and location context, "
                "produce a single concise image generation prompt optimised for "
                "Stable Diffusion / SDXL / Midjourney. "
                "Output ONLY the prompt — no explanation, no markdown. "
                "Max 100 words. End with: highly detailed, cinematic lighting, 8k."
            )
            _user = (
                f"CHARACTER: {character or 'unknown'}\n"
                f"LOCATION: {location or 'unspecified'}\n"
                f"EMOTION: {emotion or 'infer from dialog'}\n"
                f"DIALOG: \"{dialog}\"\n"
                f"{'STYLE: ' + extra_style if extra_style else ''}\n\n"
                "Generate the image prompt."
            )
            client = _anthropic.Anthropic(api_key=anthropic_key)
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=200,
                system=_system,
                messages=[{"role": "user", "content": _user}],
            )
            prompt_result = resp.content[0].text.strip()
            status2.update(label="Step 2 — Prompt generated ✅", state="complete")
        except Exception as e:
            status2.update(label=f"Step 2 — Error: {e}", state="error")
            st.error(str(e))
            st.stop()

    st.markdown(
        '<div class="step-box step-done">'
        '<div class="step-label">Step 2 — Image Prompt</div>'
        f'{prompt_result}'
        '</div>',
        unsafe_allow_html=True,
    )
    st.code(prompt_result, language=None)

    # ── STEP 3: Generate image via Pollinations.ai ───────────────────────
    image_url = None
    with st.status("Step 3 — Generating image (Pollinations.ai / nano banana)…", expanded=True) as status3:
        try:
            encoded = urllib.parse.quote(prompt_result, safe="")
            params = (
                f"?width={img_width}&height={img_height}"
                f"&model={poll_model}&nologo=true&enhance=false"
            )
            if seed > 0:
                params += f"&seed={seed}"
            image_url = f"https://image.pollinations.ai/prompt/{encoded}{params}"

            # Prefetch to verify it works
            import requests as _req
            r = _req.get(image_url, timeout=90)
            r.raise_for_status()
            status3.update(label="Step 3 — Image generated ✅", state="complete")
        except Exception as e:
            status3.update(label=f"Step 3 — Error: {e}", state="error")
            st.error(str(e))
            st.stop()

    st.markdown(
        '<div class="step-box step-done">'
        '<div class="step-label">Step 3 — Image (Pollinations.ai)</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.image(image_url, use_container_width=True)
    st.code(image_url, language=None)

    # ── STEP 4: Generate video via Replicate SVD ─────────────────────────
    video_url = None
    use_real_video = "replicate" in video_backend and replicate_token

    with st.status(
        "Step 4 — Generating video (Replicate SVD)…" if use_real_video
        else "Step 4 — Video (mock — no Replicate token)…",
        expanded=True,
    ) as status4:
        try:
            from generators.video_generator import VideoGenerator

            vg = VideoGenerator(
                replicate_token=replicate_token,
                backend="replicate" if use_real_video else "mock",
                fps=fps,
                motion_bucket_id=motion,
            )
            video_url = vg.generate(image_url)
            label = "Step 4 — Video generated ✅" if use_real_video else "Step 4 — Mock video (image URL used) ✅"
            status4.update(label=label, state="complete")
        except Exception as e:
            status4.update(label=f"Step 4 — Error: {e}", state="error")
            st.warning(f"Video generation failed: {e}")
            video_url = image_url   # graceful fallback

    st.markdown(
        '<div class="step-box step-done">'
        '<div class="step-label">Step 4 — Video</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    if video_url and video_url.endswith(".mp4"):
        st.video(video_url)
    else:
        st.image(video_url, caption="Video preview (mock — shows image)", use_container_width=True)
    st.code(video_url, language=None)

    # ── Summary table ────────────────────────────────────────────────────
    st.divider()
    st.subheader("📋 Summary — copy into Google Sheet")

    import pandas as pd
    summary = pd.DataFrame(
        [{
            "Step": "1 · Dialog",
            "Content": f"{character}: {dialog}" if character else dialog,
        }, {
            "Step": "2 · Image Prompt",
            "Content": prompt_result or "",
        }, {
            "Step": "3 · Image URL",
            "Content": image_url or "",
        }, {
            "Step": "4 · Video URL",
            "Content": video_url or "",
        }]
    )
    st.dataframe(summary, use_container_width=True, hide_index=True)
