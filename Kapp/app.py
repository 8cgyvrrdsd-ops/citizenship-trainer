import json
import random
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

try:
    from streamlit_mic_recorder import speech_to_text
except Exception:
    speech_to_text = None

APP_TITLE = "USCIS Citizenship Practice App"
DATA_DIR = Path(__file__).parent / "data"

st.set_page_config(page_title=APP_TITLE, page_icon="🇺🇸", layout="wide")


# -----------------------------
# Helpers
# -----------------------------
def load_json(filename: str) -> dict:
    path = DATA_DIR / filename
    if not path.exists():
        st.error(f"Missing data file: {path}")
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_first_existing(filenames: list[str]) -> dict:
    """Load the first matching data file. Lets GitHub users drop in a full civics file without changing code."""
    data, _filename = load_first_existing_with_name(filenames)
    return data


def load_first_existing_with_name(filenames: list[str]) -> tuple[dict, str]:
    """Load the first matching data file and return both data and the filename used."""
    for filename in filenames:
        path = DATA_DIR / filename
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f), filename
    return load_json(filenames[-1]), filenames[-1]


def normalize_civics_questions(civics_data):
    """Accept either USCIS civics JSON shape:
    1) {"questions": [{"question": "...", "answers": [...]}, ...]}
    2) [{"question": "...", "answers": [...]}, ...]
    Also tolerates common key names like answer, correct_answer, q, and a.
    """
    if isinstance(civics_data, dict):
        raw_questions = civics_data.get("questions", [])
    elif isinstance(civics_data, list):
        raw_questions = civics_data
    else:
        return []

    normalized = []
    for item in raw_questions:
        if not isinstance(item, dict):
            continue
        question = (
            item.get("question")
            or item.get("Question")
            or item.get("q")
            or item.get("prompt")
            or item.get("text")
            or ""
        )
        answers = (
            item.get("answers")
            or item.get("answer")
            or item.get("Answer")
            or item.get("correct_answers")
            or item.get("correct_answer")
            or item.get("a")
            or []
        )
        if isinstance(answers, str):
            answers = [answers]
        elif not isinstance(answers, list):
            answers = []
        answers = [str(a).strip() for a in answers if str(a).strip()]
        if str(question).strip() and answers:
            normalized.append({"question": str(question).strip(), "answers": answers})
    return normalized


def normalize(text: str) -> str:
    text = (text or "").lower().strip()
    text = text.replace("u.s.", "us")
    text = text.replace("d.c.", "dc")
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def fuzzy_score(expected: str, entered: str) -> float:
    return SequenceMatcher(None, normalize(expected), normalize(entered)).ratio()


def answer_is_blank(text: str) -> bool:
    return normalize(text) == ""


def civics_is_correct(user_answer: str, expected_answers: list[str]) -> bool:
    """Forgiving civics check, but never accepts a blank answer."""
    ans = normalize(user_answer)
    if not ans:
        return False
    for expected in expected_answers:
        exp = normalize(expected)
        if not exp:
            continue
        # Exact / containment for short official answers.
        if ans == exp or exp in ans or ans in exp:
            return True
        # Fuzzy fallback for minor spelling mistakes.
        if SequenceMatcher(None, ans, exp).ratio() >= 0.82:
            return True
    return False


def process_civics_response(answer: str, item: dict, expected_answers: list[str], source: str = "typed"):
    """Score one civics response exactly once, then update the practice flow."""
    if answer_is_blank(answer):
        st.session_state.civics_show_mc = False
        st.session_state.civics_feedback = "blank"
        st.session_state.civics_last_answer_source = source
        return

    if civics_is_correct(answer, expected_answers):
        st.session_state.civics_correct += 1
        st.session_state.civics_answered += 1
        st.session_state.civics_exam_pos += 1
        st.session_state.civics_show_mc = False
        st.session_state.civics_feedback = "correct"
        st.session_state.civics_last_answer = answer
        st.session_state.civics_last_answer_source = source
    else:
        st.session_state.civics_answered += 1
        st.session_state.civics_show_mc = True
        st.session_state.civics_feedback = "wrong"
        st.session_state.civics_last_answer = answer
        st.session_state.civics_last_answer_source = source
        st.session_state.civics_wrong_review.append({
            "question": item["question"],
            "answers": expected_answers,
            "user_answer": answer,
        })


def record_answer_box(key: str):
    """Return browser speech transcript directly to Streamlit when the mic package is available."""
    if speech_to_text is None:
        st.error("Microphone recorder package is missing. Run: pip install -r requirements.txt")
        st.caption("Fallback: type the answer in the box below.")
        return None
    return speech_to_text(
        language="en",
        start_prompt="🎙 Record answer",
        stop_prompt="⏹ Stop recording",
        just_once=True,
        use_container_width=True,
        key=key,
    )


def make_civics_choices(item: dict, all_questions: list[dict], max_choices: int = 4) -> list[str]:
    """Build a simple multiple-choice fallback: correct answer + plausible answers from other questions."""
    correct = item.get("answers", [""])[0]
    pool = []
    for q in all_questions:
        if q is item:
            continue
        for a in q.get("answers", []):
            if normalize(a) != normalize(correct):
                pool.append(a)
    random.shuffle(pool)
    choices = [correct] + pool[: max_choices - 1]
    # Remove duplicates while preserving order.
    deduped = []
    seen = set()
    for c in choices:
        n = normalize(c)
        if n and n not in seen:
            deduped.append(c)
            seen.add(n)
    random.shuffle(deduped)
    return deduped


def reset_civics_exam(questions: list[dict], session_len: int = 20):
    total = min(session_len, len(questions))
    indices = list(range(len(questions)))
    random.shuffle(indices)
    st.session_state.civics_exam_indices = indices[:total]
    st.session_state.civics_exam_pos = 0
    st.session_state.civics_correct = 0
    st.session_state.civics_answered = 0
    st.session_state.civics_wrong_review = []
    st.session_state.civics_show_mc = False
    st.session_state.civics_feedback = None
    st.session_state.civics_last_processed_voice = None
    st.session_state.civics_last_answer = ""
    st.session_state.civics_last_answer_source = None
    st.session_state.civics_mc_review_answer = False


def check_answer(expected: str, user_answer: str, strict: bool = False):
    if answer_is_blank(user_answer):
        return "Blank answer", 0.0
    score = fuzzy_score(expected, user_answer)
    exact = normalize(expected) == normalize(user_answer)
    threshold = 0.96 if strict else 0.84
    if exact:
        return "Correct", score
    if score >= threshold:
        return "Probably OK - meaning looks clear, but practice spelling", score
    return "Needs practice", score


def speak_button(text: str, label: str = "▶ Replay officer voice"):
    safe_text = json.dumps(text)
    safe_label = json.dumps(label)
    components.html(
        f"""
        <button onclick='speakText()' style='font-size:16px;padding:10px 14px;border-radius:8px;border:1px solid #999;cursor:pointer;'>
          <script>document.write({safe_label})</script>
        </button>
        <script>
        function speakText() {{
            const msg = new SpeechSynthesisUtterance({safe_text});
            msg.rate = 0.82;
            msg.pitch = 1.0;
            window.speechSynthesis.cancel();
            window.speechSynthesis.speak(msg);
        }}
        </script>
        """,
        height=55,
    )


def _speech_script_for_sequence(texts: list[str], unique_key: str, delay_ms: int = 1200, pause_ms: int = 850, cancel_first: bool = True):
    """Speak one or more text chunks once per unique key.

    Chaining utterances with a small pause reduces the common browser issue where
    the first words are quiet or clipped after a Streamlit rerun.
    """
    safe_texts = json.dumps(texts)
    safe_key = json.dumps(unique_key)
    safe_delay = int(delay_ms)
    safe_pause = int(pause_ms)
    safe_cancel = "true" if cancel_first else "false"
    components.html(
        f"""
        <script>
        const questionKey = {safe_key};
        const lastKey = window.parent.sessionStorage.getItem('last_civics_spoken_key');
        if (lastKey !== questionKey) {{
            window.parent.sessionStorage.setItem('last_civics_spoken_key', questionKey);
            const texts = {safe_texts};
            const startSpeaking = () => {{
                if ({safe_cancel}) {{ window.parent.speechSynthesis.cancel(); }}
                let i = 0;
                const speakNext = () => {{
                    if (i >= texts.length) return;
                    const msg = new SpeechSynthesisUtterance(texts[i]);
                    msg.rate = 0.78;
                    msg.pitch = 1.0;
                    msg.volume = 1.0;
                    i += 1;
                    msg.onend = () => setTimeout(speakNext, {safe_pause});
                    window.parent.speechSynthesis.speak(msg);
                }};
                // Give the browser audio engine a moment after cancel/rerun before speaking.
                setTimeout(speakNext, 250);
            }};
            const waitForVoicesThenSpeak = () => {{
                try {{ window.parent.speechSynthesis.getVoices(); }} catch(e) {{}}
                setTimeout(startSpeaking, {safe_delay});
            }};
            waitForVoicesThenSpeak();
        }}
        </script>
        """,
        height=0,
    )


def auto_speak_once(text: str, unique_key: str, delay_ms: int = 1200, cancel_first: bool = True):
    """Automatically speak text once per unique key."""
    _speech_script_for_sequence([text], unique_key, delay_ms=delay_ms, pause_ms=0, cancel_first=cancel_first)


def auto_speak_sequence_once(texts: list[str], unique_key: str, delay_ms: int = 1200, pause_ms: int = 850, cancel_first: bool = True):
    """Automatically speak a short sequence once per unique key."""
    _speech_script_for_sequence(texts, unique_key, delay_ms=delay_ms, pause_ms=pause_ms, cancel_first=cancel_first)

def browser_speech_box(box_id: str, label: str = "🎙 Record answer with browser speech"):
    """Browser-only speech-to-text helper. User copies transcript into Streamlit answer field."""
    components.html(
        f"""
        <div style="border:1px solid #444;border-radius:10px;padding:12px;margin:4px 0 14px 0;">
          <button id="start_{box_id}" style="font-size:16px;padding:9px 12px;border-radius:8px;border:1px solid #999;cursor:pointer;">{label}</button>
          <button id="copy_{box_id}" style="font-size:16px;padding:9px 12px;border-radius:8px;border:1px solid #999;cursor:pointer;margin-left:8px;">Copy transcript</button>
          <div id="status_{box_id}" style="margin-top:8px;font-size:14px;opacity:.85;">Click record, answer out loud, then copy/paste the transcript below.</div>
          <textarea id="text_{box_id}" style="width:100%;height:70px;margin-top:8px;border-radius:8px;padding:8px;font-size:16px;" placeholder="Transcript will appear here if your browser supports speech recognition."></textarea>
        </div>
        <script>
        const startBtn = document.getElementById('start_{box_id}');
        const copyBtn = document.getElementById('copy_{box_id}');
        const status = document.getElementById('status_{box_id}');
        const textBox = document.getElementById('text_{box_id}');
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {{
          status.innerText = 'Browser speech recognition is not available here. Type the answer below instead.';
          startBtn.disabled = true;
        }} else {{
          const rec = new SpeechRecognition();
          rec.lang = 'en-US';
          rec.interimResults = false;
          rec.maxAlternatives = 1;
          startBtn.onclick = function() {{
            textBox.value = '';
            status.innerText = 'Listening... speak now.';
            rec.start();
          }};
          rec.onresult = function(event) {{
            textBox.value = event.results[0][0].transcript;
            status.innerText = 'Done. Copy/paste transcript into the answer box below.';
          }};
          rec.onerror = function(event) {{
            status.innerText = 'Speech error: ' + event.error + '. You can type the answer below.';
          }};
          rec.onend = function() {{
            if (!textBox.value) status.innerText = 'Stopped. No transcript captured. Try again or type the answer below.';
          }};
        }}
        copyBtn.onclick = async function() {{
          try {{
            await navigator.clipboard.writeText(textBox.value);
            status.innerText = 'Copied. Paste it into the answer box below.';
          }} catch(e) {{
            textBox.select();
            document.execCommand('copy');
            status.innerText = 'Copied. Paste it into the answer box below.';
          }}
        }};
        </script>
        """,
        height=180,
    )


def big_card(title: str, body: str, border: bool = True):
    border_css = "border: 1px solid #ddd;" if border else ""
    st.markdown(
        f"""
        <div style='{border_css} border-radius:12px; padding:18px; margin:8px 0; background:rgba(250,250,250,.65);'>
          <div style='font-size:0.9rem; color:#666;'>{title}</div>
          <div style='font-size:1.6rem; font-weight:700; margin-top:4px;'>{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def colored_result(text: str, ok: bool):
    color = "#18a558" if ok else "#d93025"
    st.markdown(f"<div style='font-weight:700;color:{color};'>{text}</div>", unsafe_allow_html=True)


# -----------------------------
# Load data
# -----------------------------
reading = load_json("reading_vocab_m715.json")
writing = load_json("writing_practice.json")
n400_vocab = load_json("n400_vocab_self_test2.json")
n400_personal = load_json("n400_personal_prompts.json")
# Civics is loaded inside the Civics Practice module so the user can switch
# between the standard question file and the hard/reworded question file.

with st.sidebar:
    st.title("🇺🇸 Citizenship Practice")
    module = st.radio(
        "Choose section",
        [
            "Home / Coverage",
            "Civics Practice",
            "N-400 Interview Practice",
            "N-400 Vocabulary",
            "Reading Test Practice",
            "Writing Test Practice",
        ],
    )
    st.divider()
    st.caption("Privacy: this build contains no personal information. Personal answers typed during practice are not saved to files.")

st.title(APP_TITLE)

# -----------------------------
# Home
# -----------------------------
if module == "Home / Coverage":
    st.subheader("Build Coverage")
    st.write("This build uses generic USCIS practice data only. No personal information is stored in the JSON files.")

    col1, col2, col3 = st.columns(3)
    with col1:
        total_reading_words = sum(len(v) for v in reading.get("categories", {}).values())
        big_card("M-715 Reading Vocabulary", f"{total_reading_words} words")
    with col2:
        total_writing_words = sum(len(v) for v in writing.get("categories", {}).values())
        big_card("Writing Vocabulary", f"{total_writing_words} words")
    with col3:
        big_card("N-400 Self-Test 2", f"{len(n400_vocab.get('key_words', []))} key words")

    st.markdown("### Modules included")
    st.markdown(
        """
        - **Civics Practice**: officer voice, mic recording, automatic transcript verification, multiple-choice fallback, 20-question scoring.
        - **N-400 Interview Practice**: generic prompts only; recommended as speak-aloud practice, not saved-answer practice.
        - **N-400 Vocabulary**: Self-Test 2 meaning quiz, matching, fill-in conversation, and word list.
        - **Reading Test Practice**: M-715 flashcards, reading sentences, test simulation, and coverage list.
        - **Writing Test Practice**: dictation with forgiving answer check and next-question flow.
        """
    )
    st.success("PI check: data files contain only generic practice content and placeholders like [your full name].")

# -----------------------------
# Civics
# -----------------------------
elif module == "Civics Practice":
    st.subheader("Civics Practice")
    st.write("Practice exam flow: answer the officer question by voice. Correct answers score and move forward. Wrong answers show a multiple-choice fallback.")

    use_hard_questions = st.toggle("Use hard/reworded civics questions", value=False)
    if use_hard_questions:
        civics, civics_filename = load_first_existing_with_name(["questions_hard.json"])
        st.caption(f"Question source: hard/reworded file — `{civics_filename}`")
    else:
        # Default must be the standard USCIS question file. Only fall back if it is not present.
        civics, civics_filename = load_first_existing_with_name(["questions.json"])
        st.caption(f"Question source: standard file — `{civics_filename}`")

    questions = normalize_civics_questions(civics)
    session_len = min(20, len(questions))

    if not questions:
        if use_hard_questions:
            st.error("No hard civics questions found. Add data/questions_hard.json, or turn off hard/reworded questions.")
        else:
            st.error("No standard civics questions found. Add data/questions.json. This build does not use civics_sample.json.")
    else:
        civics_source_key = f"{'hard' if use_hard_questions else 'standard'}:{civics_filename}:{len(questions)}"
        if (
            "civics_exam_indices" not in st.session_state
            or not st.session_state.civics_exam_indices
            or st.session_state.get("civics_source_key") != civics_source_key
        ):
            reset_civics_exam(questions, session_len=20)
            st.session_state.civics_source_key = civics_source_key
            st.session_state.civics_last_recorder_text = ""

        # If the session is complete, allow a clean restart.
        if st.session_state.civics_exam_pos >= len(st.session_state.civics_exam_indices):
            st.success("Civics practice session complete.")
            st.metric("Final score", f"{st.session_state.civics_correct} / {st.session_state.civics_answered}")
            if st.session_state.civics_wrong_review:
                with st.expander("Review missed questions"):
                    for row in st.session_state.civics_wrong_review:
                        st.markdown(f"**Question:** {row['question']}")
                        st.markdown(f"**Acceptable answer:** {', '.join(row['answers'])}")
                        st.markdown(f"**Your answer:** {row.get('user_answer') or 'No typed answer'}")
                        st.divider()
            if st.button("Start new 20-question civics practice"):
                reset_civics_exam(questions, session_len=20)
                st.rerun()
        else:
            pos = st.session_state.civics_exam_pos
            q_index = st.session_state.civics_exam_indices[pos]
            item = questions[q_index]
            expected_answers = item.get("answers", [])

            col1, col2, col3 = st.columns(3)
            col1.metric("Question", f"{pos + 1} / {len(st.session_state.civics_exam_indices)}")
            col2.metric("Score", f"{st.session_state.civics_correct} / {st.session_state.civics_answered}")
            remaining = len(st.session_state.civics_exam_indices) - pos
            col3.metric("Remaining", remaining)

            feedback = st.session_state.get("civics_feedback")
            just_got_correct = feedback in ("correct", "mc_correct")
            if just_got_correct:
                st.success("Correct. Next question.")
                # Audio cleanup: do NOT speak the confirmation and the next question in the
                # same browser speech queue. That was causing clipped/choppy audio after
                # Streamlit reruns and mic component refreshes.
                #
                # Step 1: speak only the confirmation.
                auto_speak_once(
                    "Correct. Next question.",
                    f"civics_correct_confirm_{pos}_{q_index}_{st.session_state.civics_answered}",
                    delay_ms=350,
                    cancel_first=True,
                )
                # Step 2: give the browser time to finish speaking before a clean rerun.
                # On the next clean rerun, the officer question is asked by the normal
                # auto_speak_once block below.
                st.session_state.civics_feedback = None
                time.sleep(2.2)
                st.rerun()
            else:
                # First load / normal question change: officer asks automatically after a
                # longer delay so browser audio and the mic component can finish initializing.
                auto_speak_once(item["question"], f"civics_question_{pos}_{q_index}_{civics_filename}", delay_ms=2000, cancel_first=True)

            st.markdown("### Listen to the officer question")
            speak_button(item["question"], label="▶ Replay officer question")
            st.markdown("### Answer by voice")
            st.caption("Click Record, answer out loud, then stop. The app shows what it heard and checks the answer automatically.")

            # Keep one stable recorder component. Changing the key can make the browser ask
            # for microphone permission again on every question.
            transcript = record_answer_box("civics_voice_recorder_stable")
            if transcript:
                clean_transcript = normalize(transcript)
                last_recorder_text = st.session_state.get("civics_last_recorder_text", "")
                processed_key = f"{pos}|{q_index}|{clean_transcript}"
                # With a stable component key, Streamlit may briefly replay the previous transcript
                # after a rerun. Ignore it until the student records something new.
                if clean_transcript and clean_transcript != last_recorder_text:
                    st.info(f"Heard: {transcript}")
                    if st.session_state.get("civics_last_processed_voice") != processed_key:
                        st.session_state.civics_last_processed_voice = processed_key
                        st.session_state.civics_last_recorder_text = clean_transcript
                        process_civics_response(transcript, item, expected_answers, source="voice")
                        if answer_is_blank(transcript):
                            st.error("No answer heard. Blank answers do not pass.")
                        else:
                            st.rerun()

            if st.session_state.get("civics_feedback") == "wrong" and st.session_state.get("civics_show_mc"):
                st.warning("Not quite. Try the multiple-choice fallback.")
                if f"civics_choices_{pos}" not in st.session_state:
                    st.session_state[f"civics_choices_{pos}"] = make_civics_choices(item, questions)
                choices = st.session_state[f"civics_choices_{pos}"]
                mc = st.radio("Choose an acceptable answer:", choices, key=f"civics_mc_{pos}")
                if "civics_mc_review_answer" not in st.session_state:
                    st.session_state.civics_mc_review_answer = False

                if st.button("Check multiple choice"):
                    if any(normalize(mc) == normalize(a) for a in expected_answers):
                        st.session_state.civics_correct += 1
                        # Multiple-choice recovery counts as correct for practice score, but the miss stays in review.
                        st.session_state.civics_exam_pos += 1
                        st.session_state.civics_show_mc = False
                        st.session_state.civics_feedback = "mc_correct"
                        st.session_state.civics_mc_review_answer = False
                        st.rerun()
                    else:
                        st.session_state.civics_mc_review_answer = True
                        st.error("Still not correct. Review the acceptable answer below.")

                # Do not show the correct answer before the student tries multiple choice.
                # Show it only after the multiple-choice answer is also incorrect.
                if st.session_state.get("civics_mc_review_answer"):
                    st.markdown("### Correct answer review")
                    st.success(", ".join(expected_answers))
                    st.caption("In the real civics test, many questions have more than one acceptable answer. She only needs to give one acceptable answer.")

                    st.divider()
                    if st.button("Next question", type="primary"):
                        st.session_state.civics_exam_pos += 1
                        st.session_state.civics_show_mc = False
                        st.session_state.civics_feedback = None
                        st.session_state.civics_mc_review_answer = False
                        st.rerun()

            with st.expander("Session controls"):
                st.write(f"This practice session asks up to **20 questions** from **{civics_filename}**. Current data file has **{len(questions)} questions**, so this session has **{len(st.session_state.civics_exam_indices)}** questions.")
                if st.button("Restart civics practice"):
                    reset_civics_exam(questions, session_len=20)
                    st.rerun()

# -----------------------------
# N-400 Personal Interview
# -----------------------------
elif module == "N-400 Interview Practice":
    st.subheader("N-400 Interview Practice")
    st.warning(
        "Privacy recommendation: use this section mainly for speak-aloud practice. Do not type real personal answers into a public/shared app. The app does not save answers, but the safest habit is to avoid entering PI."
    )

    prompts = n400_personal.get("prompts", [])
    topic_filter = st.selectbox("Topic", ["All"] + sorted(set(p["topic"] for p in prompts)))
    filtered = prompts if topic_filter == "All" else [p for p in prompts if p["topic"] == topic_filter]

    if "n400_idx" not in st.session_state:
        st.session_state.n400_idx = 0
    if filtered:
        col_a, col_b = st.columns([1, 1])
        with col_a:
            if st.button("Random N-400 question"):
                st.session_state.n400_idx = random.randrange(len(filtered))
        with col_b:
            if st.button("Next N-400 question"):
                st.session_state.n400_idx = (st.session_state.n400_idx + 1) % len(filtered)

        p = filtered[st.session_state.n400_idx % len(filtered)]
        speak_button(p["question"])
        big_card(p["topic"], p["question"])
        st.caption("Recommended: the student answers out loud. Use the pattern only as a guide. No verification is attempted here because personal N-400 answers must match her actual application.")

        practice_mode = st.radio(
            "Practice method",
            ["Speak aloud only - safest", "Type a temporary practice answer - not saved"],
            horizontal=True,
        )
        if practice_mode.startswith("Type"):
            st.text_area("Temporary practice answer. Do not enter PI on a public/shared app:", height=100, key="n400_practice_text")
        with st.expander("Show simple answer pattern"):
            st.write(p["sample_answer"])
    else:
        st.error("No N-400 prompts found.")

# -----------------------------
# N-400 Vocabulary
# -----------------------------
elif module == "N-400 Vocabulary":
    st.subheader("N-400 Vocabulary for the Naturalization Interview")
    mode = st.tabs(["Meaning Quiz", "Matching", "Fill in Conversation", "Word List"])

    with mode[0]:
        st.markdown("### Self-Test 2: Choose similar meaning")
        questions = n400_vocab.get("multiple_choice", [])
        if "vocab_mc_idx" not in st.session_state:
            st.session_state.vocab_mc_idx = 0
        if "vocab_mc_feedback" not in st.session_state:
            st.session_state.vocab_mc_feedback = None

        col_a, col_b = st.columns([1, 1])
        with col_a:
            if st.button("Random vocabulary question", key="mc_random"):
                st.session_state.vocab_mc_idx = random.randrange(len(questions))
                st.session_state.vocab_mc_feedback = None
        with col_b:
            if st.button("Next vocabulary question", key="mc_next"):
                st.session_state.vocab_mc_idx = (st.session_state.vocab_mc_idx + 1) % len(questions)
                st.session_state.vocab_mc_feedback = None

        if questions:
            q = questions[st.session_state.vocab_mc_idx % len(questions)]
            speak_button(q["question"])
            big_card("Question", q["question"])
            choice = st.radio("Choose the best meaning", q["choices"], key=f"mc_{st.session_state.vocab_mc_idx}")
            if st.button("Check answer", key="check_mc"):
                if choice == q["answer"]:
                    st.session_state.vocab_mc_feedback = ("correct", q["answer"])
                    st.success("Correct. Moving to the next question...")
                    st.session_state.vocab_mc_idx = (st.session_state.vocab_mc_idx + 1) % len(questions)
                    st.session_state.vocab_mc_feedback = None
                    st.rerun()
                else:
                    st.session_state.vocab_mc_feedback = ("wrong", q["answer"])

            feedback = st.session_state.get("vocab_mc_feedback")
            if feedback and feedback[0] == "wrong":
                st.error("Incorrect.")
                st.markdown(f"**Correct answer:** {feedback[1]}")
                key_word = q["question"].split("—")[0].strip()
                meanings = {item["word"]: item for item in n400_vocab.get("key_words", [])}
                if key_word in meanings:
                    st.info(f"{key_word} means: {meanings[key_word]['meaning']}. Example: {meanings[key_word]['example']}")

    with mode[1]:
        st.markdown("### Student Handout B: Matching")
        match = n400_vocab.get("matching", {})
        terms = match.get("terms", [])
        defs = match.get("definitions", [])
        answers = match.get("answers", {})
        st.write("Match each word to the best meaning.")
        responses = {}
        for term in terms:
            responses[term] = st.selectbox(term, [""] + defs, key=f"match_{term}")
        if st.button("Check matching answers"):
            correct = 0
            wrong_rows = []
            for term, response in responses.items():
                expected = answers.get(term)
                if response == expected:
                    correct += 1
                else:
                    wrong_rows.append((term, response or "No answer", expected))
            st.success(f"Score: {correct} / {len(terms)}")
            if wrong_rows:
                st.markdown("### Wrong answers to review")
                for term, response, expected in wrong_rows:
                    st.markdown(f"**{term}**")
                    st.markdown(f"Your answer: {response}")
                    st.markdown(f"Correct answer: {expected}")
                    st.divider()

    with mode[2]:
        st.markdown("### Student Handout A: Fill in the Conversation")
        items = n400_vocab.get("fill_in_conversation", [])
        st.write("Type the missing word or phrase. Feedback appears under each item after you check answers.")
        for i, item in enumerate(items, 1):
            st.write(f"{i}. {item['sentence']}")
            st.text_input("Your answer", key=f"fill_{i}")
        if st.button("Check fill-in answers"):
            for i, item in enumerate(items, 1):
                user_ans = st.session_state.get(f"fill_{i}", "")
                expected = item["answer"]
                ok = normalize(user_ans) == normalize(expected)
                st.markdown(f"**{i}. {item['sentence']}**")
                if ok:
                    colored_result(f"Correct: {expected}", True)
                else:
                    colored_result(f"Incorrect. Your answer: {user_ans or 'No answer'}", False)
                    colored_result(f"Correct answer: {expected}", True)

    with mode[3]:
        st.markdown("### Key words and meanings")
        st.info("For now this is a simple study list. We will brainstorm a better interactive use later.")
        for item in n400_vocab.get("key_words", []):
            st.write(f"**{item['word']}** = {item['meaning']}")
            st.caption(item["example"])

# -----------------------------
# Reading
# -----------------------------
elif module == "Reading Test Practice":
    st.subheader("M-715 Reading Test Practice")
    tabs = st.tabs(["Flashcards", "Sentence Reading", "Test Simulation", "Coverage"])

    with tabs[0]:
        st.markdown("### Word Flashcards")
        st.info("Current purpose: word recognition and pronunciation. We will brainstorm the best interaction later.")
        categories = reading.get("categories", {})
        cat = st.selectbox("Category", list(categories.keys()))
        words = categories.get(cat, [])
        word = st.selectbox("Word", words)
        speak_button(word, "▶ Hear word")
        big_card(cat, word)
        st.caption("Student reads this word aloud.")

    with tabs[1]:
        st.markdown("### Reading sentences")
        st.info("Current purpose: practice reading complete USCIS-style sentences aloud. We will brainstorm improvements later.")
        sentences = reading.get("sentences", [])
        if "reading_sentence_idx" not in st.session_state:
            st.session_state.reading_sentence_idx = 0
        if st.button("Random reading sentence"):
            st.session_state.reading_sentence_idx = random.randrange(len(sentences))
        sentence = sentences[st.session_state.reading_sentence_idx % len(sentences)]
        big_card("Student reads aloud", sentence)
        speak_button(sentence, "▶ Hear sentence after trying")

    with tabs[2]:
        st.markdown("### Reading test simulation")
        st.info("Current purpose: show up to 3 sentences, similar to the real test format. We will brainstorm improvements later.")
        st.write("USCIS-style practice: show up to 3 sentences. Student only needs to read 1 correctly in the real test.")
        if st.button("Generate 3 reading sentences"):
            st.session_state.reading_test = random.sample(reading.get("sentences", []), k=min(3, len(reading.get("sentences", []))))
        for i, s in enumerate(st.session_state.get("reading_test", []), 1):
            big_card(f"Sentence {i}", s)

    with tabs[3]:
        st.markdown("### Official M-715 vocabulary coverage")
        for cat, words in reading.get("categories", {}).items():
            with st.expander(f"{cat} — {len(words)} words"):
                st.write(", ".join(words))

# -----------------------------
# Writing
# -----------------------------
elif module == "Writing Test Practice":
    st.subheader("Writing Test Practice")
    st.write("Officer voice dictates a sentence. Student types what they hear. Practice mode checks spelling more strictly; Interview-style mode allows small errors if the meaning is clear.")

    sentences = writing.get("sentences", [])
    categories = writing.get("categories", {})
    tabs = st.tabs(["Dictation", "Vocabulary Coverage"])

    with tabs[0]:
        strict = st.toggle("Practice strict spelling mode", value=False)
        if "writing_idx" not in st.session_state:
            st.session_state.writing_idx = 0
        if "writing_feedback" not in st.session_state:
            st.session_state.writing_feedback = None

        col_a, col_b = st.columns([1, 1])
        with col_a:
            if st.button("Random writing sentence"):
                st.session_state.writing_idx = random.randrange(len(sentences))
                st.session_state.writing_feedback = None
        with col_b:
            if st.button("Next writing sentence"):
                st.session_state.writing_idx = (st.session_state.writing_idx + 1) % len(sentences)
                st.session_state.writing_feedback = None
                st.session_state.writing_typed = ""

        target = sentences[st.session_state.writing_idx % len(sentences)]
        speak_button(target, "▶ Officer says sentence")
        st.caption("Listen first. Type the sentence below. Use Show sentence only after trying.")
        typed = st.text_input("Type the sentence here:", key="writing_typed")

        if st.button("Check writing"):
            result, score = check_answer(target, typed, strict=strict)
            st.session_state.writing_feedback = (result, score, typed, target)

        feedback = st.session_state.get("writing_feedback")
        if feedback:
            result, score, old_typed, old_target = feedback
            if result == "Correct":
                st.success(f"{result}. Score: {score:.0%}")
                st.session_state.writing_idx = (st.session_state.writing_idx + 1) % len(sentences)
                st.session_state.writing_feedback = None
                st.session_state.writing_typed = ""
                st.rerun()
            elif result.startswith("Probably"):
                st.info(f"{result}. Score: {score:.0%}")
                st.write("Expected:", old_target)
                st.write("Typed:", old_typed)
                if st.button("Accept and move to next writing sentence"):
                    st.session_state.writing_idx = (st.session_state.writing_idx + 1) % len(sentences)
                    st.session_state.writing_feedback = None
                    st.session_state.writing_typed = ""
                    st.rerun()
            elif result == "Blank answer":
                st.error("No answer entered. Try again or show the sentence after trying.")
            else:
                st.warning(f"{result}. Score: {score:.0%}")
                st.write("Expected:", old_target)
                st.write("Typed:", old_typed)
                if st.button("Move to next writing sentence anyway"):
                    st.session_state.writing_idx = (st.session_state.writing_idx + 1) % len(sentences)
                    st.session_state.writing_feedback = None
                    st.session_state.writing_typed = ""
                    st.rerun()

        with st.expander("Show sentence"):
            st.write(target)

    with tabs[1]:
        st.markdown("### Writing vocabulary coverage")
        for cat, words in categories.items():
            with st.expander(f"{cat} — {len(words)} words"):
                st.write(", ".join(words))

st.divider()
st.caption("Build note: This app uses local JSON files only. It does not require API keys and does not store personal answers.")
