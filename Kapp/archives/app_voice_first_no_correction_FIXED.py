import json
import random
import re
import subprocess
import tempfile
from difflib import SequenceMatcher
from pathlib import Path
from datetime import datetime

import streamlit as st

try:
    import speech_recognition as sr
except ImportError:
    sr = None

APP_TITLE = "Ket's Citizenship Trainer"
QUESTIONS_FILE = Path("questions.json")
PROGRESS_FILE = Path("progress.json")

SESSION_LENGTH = 20
PASSING_SCORE = 12
MAX_SPOKEN_ATTEMPTS = 2

# QA mode: set to False when ready to use questions.json again
USE_TEST_QUESTIONS = True

TEST_QUESTIONS = [
    {
        "id": 9001,
        "section": "QA Test",
        "category": "Simple Colors",
        "question": "Apples are what color?",
        "answers": ["red", "green"],
        "special_65_20": False,
    },
    {
        "id": 9002,
        "section": "QA Test",
        "category": "Simple Colors",
        "question": "The sky is what color?",
        "answers": ["blue"],
        "special_65_20": False,
    },
    {
        "id": 9003,
        "section": "QA Test",
        "category": "Simple Numbers",
        "question": "How many wheels does a bicycle have?",
        "answers": ["two", "2"],
        "special_65_20": False,
    },
    {
        "id": 9004,
        "section": "QA Test",
        "category": "Simple Animals",
        "question": "A dog says what sound?",
        "answers": ["bark", "woof"],
        "special_65_20": False,
    },
    {
        "id": 9005,
        "section": "QA Test",
        "category": "Simple Facts",
        "question": "Ice is hot or cold?",
        "answers": ["cold"],
        "special_65_20": False,
    },
]

INTERVIEWER_VOICES = [
    {"name": "Samantha", "label": "Interviewer A - Clear female voice"},
    {"name": "Alex", "label": "Interviewer B - Clear male voice"},
    {"name": "Victoria", "label": "Interviewer C - Formal female voice"},
    {"name": "Daniel", "label": "Interviewer D - Formal male voice"},
]

FALLBACK_QUESTIONS = [
    {
        "id": 1,
        "section": "American Government",
        "category": "A: Principles of American Government",
        "question": "What is the supreme law of the land?",
        "answers": ["(U.S.) Constitution"],
        "special_65_20": True,
    },
    {
        "id": 2,
        "section": "American Government",
        "category": "A: Principles of American Government",
        "question": "What is the form of government of the United States?",
        "answers": ["Republic", "Constitution-based federal republic", "Representative democracy"],
        "special_65_20": False,
    },
]

CONFIDENCE_MESSAGES = [
    "You KNOW the material. Slow down and trust yourself.",
    "Breathe first. Then answer simple.",
    "Don’t rush. You already know more than you think.",
    "Say the short answer clearly. That is enough.",
]


# -----------------------------
# File helpers
# -----------------------------

def load_questions():
    if USE_TEST_QUESTIONS:
        return TEST_QUESTIONS
    if QUESTIONS_FILE.exists():
        return json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    return FALLBACK_QUESTIONS


def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {"questions": {}, "sessions": [], "created_at": datetime.now().isoformat()}


def save_progress(progress):
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2), encoding="utf-8")


def get_question_stats(progress, question_id):
    """
    Returns question stats and safely upgrades old progress.json records.

    Older versions used:
      seen / correct / missed

    New version uses:
      seen / spoken_correct / knowledge_correct / missed / review_needed
    """
    defaults = {
        "seen": 0,
        "spoken_correct": 0,
        "knowledge_correct": 0,
        "missed": 0,
        "review_needed": 0,
        "last_seen": None,
    }

    stats = progress["questions"].get(str(question_id), {}).copy()

    # Upgrade old progress format.
    old_correct = stats.get("correct", 0)
    if old_correct and "spoken_correct" not in stats:
        stats["spoken_correct"] = old_correct
    if old_correct and "knowledge_correct" not in stats:
        stats["knowledge_correct"] = old_correct

    for key, value in defaults.items():
        stats.setdefault(key, value)

    return stats


def update_question(progress, question_id, result):
    key = str(question_id)
    stats = get_question_stats(progress, question_id)

    stats["seen"] += 1

    if result == "spoken_correct":
        stats["spoken_correct"] += 1
        stats["knowledge_correct"] += 1
    elif result == "knowledge_correct":
        stats["knowledge_correct"] += 1
        stats["review_needed"] += 1
    elif result == "missed":
        stats["missed"] += 1

    stats["last_seen"] = datetime.now().isoformat()
    progress["questions"][key] = stats
    save_progress(progress)


# -----------------------------
# Session/question selection
# -----------------------------

def weakness_score(progress, question):
    stats = get_question_stats(progress, question["id"])

    if stats["seen"] == 0:
        return 100

    missed = stats.get("missed", 0)
    review = stats.get("review_needed", 0)
    spoken_correct = stats.get("spoken_correct", 0)

    return (missed * 4) + (review * 2) - spoken_correct + max(0, 3 - stats["seen"])


def build_session_questions(progress, mode, questions, special_only=False):
    pool = [q for q in questions if q.get("special_65_20")] if special_only else questions.copy()
    if not pool:
        pool = questions.copy()

    if mode == "Weak Questions First":
        ranked = sorted(pool, key=lambda q: weakness_score(progress, q), reverse=True)
        return ranked[: min(SESSION_LENGTH, len(ranked))]

    random.shuffle(pool)
    return pool[: min(SESSION_LENGTH, len(pool))]


def fresh_choice_key():
    return f"choice_{random.randint(100000, 999999)}"


def fresh_answer_key():
    return f"answer_{random.randint(100000, 999999)}"


def start_new_session(mode, questions, special_only=False):
    progress = load_progress()

    st.session_state.session_questions = build_session_questions(progress, mode, questions, special_only)
    st.session_state.current_index = 0
    st.session_state.session_results = []

    st.session_state.revealed = False
    st.session_state.submitted = False
    st.session_state.test_finished = False
    st.session_state.started = False

    st.session_state.spoken_index = None
    st.session_state.choice_widget_key = fresh_choice_key()
    st.session_state.answer_widget_key = fresh_answer_key()
    st.session_state.current_choices = None

    st.session_state.spoken_attempts = 0
    st.session_state.transcript = ""
    st.session_state.attempt_log = []
    st.session_state.last_validation = None

    st.session_state.interviewer_voice = random.choice(INTERVIEWER_VOICES)


def current_question():
    return st.session_state.session_questions[st.session_state.current_index]


def reset_question_state_for_retry():
    st.session_state.transcript = ""
    st.session_state.answer_widget_key = fresh_answer_key()
    st.session_state.spoken_index = None


def move_to_next_question():
    st.session_state.current_index += 1

    st.session_state.revealed = False
    st.session_state.submitted = False
    st.session_state.choice_widget_key = fresh_choice_key()
    st.session_state.answer_widget_key = fresh_answer_key()
    st.session_state.current_choices = None

    st.session_state.spoken_attempts = 0
    st.session_state.transcript = ""
    st.session_state.attempt_log = []
    st.session_state.last_validation = None

    if st.session_state.current_index >= len(st.session_state.session_questions):
        st.session_state.test_finished = True


# -----------------------------
# Audio / speech
# -----------------------------

def speak_text_mac(text, voice_name=None):
    try:
        command = ["say"]
        if voice_name:
            command.extend(["-v", voice_name])
        command.append(text)
        subprocess.Popen(command)
        return True
    except Exception:
        return False


def transcribe_audio(audio_file):
    if sr is None:
        return "", "SpeechRecognition is not installed yet."

    try:
        recognizer = sr.Recognizer()
        audio_bytes = audio_file.getvalue()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(audio_bytes)
            temp_audio_path = temp_audio.name

        with sr.AudioFile(temp_audio_path) as source:
            audio_data = recognizer.record(source)

        text = recognizer.recognize_google(audio_data)
        return text, None

    except Exception as exc:
        return "", str(exc)


# -----------------------------
# Answer matching
# -----------------------------

def clean_answer(answer):
    return answer.replace("(U.S.)", "U.S.").replace("(United States)", "United States").strip()


def normalize_text(text):
    text = text.lower()
    text = text.replace("u.s.", "us").replace("united states", "us")
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def validate_spoken_answer(transcript, accepted_answers):
    spoken = normalize_text(transcript)

    if not spoken:
        return {
            "correct": False,
            "close": False,
            "best_answer": "",
            "score": 0,
        }

    best = {
        "correct": False,
        "close": False,
        "best_answer": "",
        "score": 0,
    }

    for answer in accepted_answers:
        expected = normalize_text(clean_answer(answer))

        if not expected:
            continue

        similarity = SequenceMatcher(None, spoken, expected).ratio()

        spoken_words = set(spoken.split())
        expected_words = set(expected.split())
        overlap = len(spoken_words & expected_words) / max(1, len(expected_words))

        score = max(similarity, overlap)

        correct = score >= 0.72 or expected in spoken or spoken in expected
        close = 0.55 <= score < 0.72

        if score > best["score"]:
            best = {
                "correct": correct,
                "close": close,
                "best_answer": clean_answer(answer),
                "score": round(score, 2),
            }

    return best


def make_choices(question, all_questions):
    correct_answer = clean_answer(question["answers"][0])
    wrong_pool = []

    for q in all_questions:
        if q["id"] == question["id"] or not q.get("answers"):
            continue

        candidate = clean_answer(q["answers"][0])

        if candidate and candidate.lower() != correct_answer.lower() and len(candidate) <= 80:
            wrong_pool.append(candidate)

    random.shuffle(wrong_pool)

    choices = [correct_answer] + wrong_pool[:3]
    random.shuffle(choices)

    return choices


def is_correct_choice(selected_choice, accepted_answers):
    if not selected_choice:
        return False

    selected = selected_choice.strip().lower()

    return any(
        selected == clean_answer(answer).lower()
        or selected == answer.strip().lower()
        for answer in accepted_answers
    )


def build_result_record(question, final_result, final_answer=None, mc_answer=None):
    attempts = st.session_state.get("attempt_log", [])
    last_validation = st.session_state.get("last_validation") or {}

    return {
        "question": question,
        "final_result": final_result,
        "correct": final_result in ["spoken_correct", "knowledge_correct"],
        "spoken_correct": final_result == "spoken_correct",
        "knowledge_correct": final_result in ["spoken_correct", "knowledge_correct"],
        "multiple_choice_used": final_result == "knowledge_correct",
        "selected": final_answer or mc_answer or "",
        "multiple_choice_answer": mc_answer or "",
        "attempts": attempts,
        "attempt_count": len(attempts),
        "best_match": last_validation.get("best_answer", ""),
        "best_score": last_validation.get("score", 0),
        "review_type": (
            "none"
            if final_result == "spoken_correct"
            else "pronunciation_or_transcription_review"
            if final_result == "knowledge_correct"
            else "knowledge_review"
        ),
        "timestamp": datetime.now().isoformat(),
    }


# -----------------------------
# Streamlit UI
# -----------------------------

st.set_page_config(page_title=APP_TITLE, page_icon="🇺🇸", layout="centered")

st.title("🇺🇸 Ket's Citizenship Trainer")
st.caption("Voice-first interview trainer prototype. QA mode uses simple test questions until we switch back to USCIS questions.")

questions = load_questions()
progress = load_progress()

with st.sidebar:
    st.header("Practice Settings")

    mode = st.radio("Mode", ["Random Practice", "Weak Questions First"])
    special_only = st.toggle("65/20 special questions only", value=False)

    st.divider()
    st.subheader("Overall Progress")

    total_seen = sum(q.get("seen", 0) for q in progress["questions"].values())
    total_spoken_correct = sum(q.get("spoken_correct", 0) for q in progress["questions"].values())
    total_knowledge_correct = sum(q.get("knowledge_correct", 0) for q in progress["questions"].values())
    total_missed = sum(q.get("missed", 0) for q in progress["questions"].values())
    total_review_needed = sum(q.get("review_needed", 0) for q in progress["questions"].values())

    spoken_accuracy = round((total_spoken_correct / total_seen) * 100, 1) if total_seen else 0
    knowledge_accuracy = round((total_knowledge_correct / total_seen) * 100, 1) if total_seen else 0

    st.metric("Questions practiced", total_seen)
    st.metric("Spoken accuracy", f"{spoken_accuracy}%")
    st.metric("Knowledge accuracy", f"{knowledge_accuracy}%")
    st.metric("Needs review", total_review_needed)
    st.metric("Missed", total_missed)

    st.write(f"Question bank loaded: **{len(questions)}**")

    if USE_TEST_QUESTIONS:
        st.warning("QA mode is ON: using simple test questions, not USCIS questions.")

    if st.button("Start New Test"):
        start_new_session(mode, questions, special_only)
        st.rerun()

    if st.button("Reset All Progress"):
        save_progress({"questions": {}, "sessions": [], "created_at": datetime.now().isoformat()})
        st.session_state.clear()
        st.rerun()


if "session_questions" not in st.session_state:
    start_new_session(mode, questions, special_only)


# -----------------------------
# End-of-test report
# -----------------------------

if st.session_state.test_finished:
    results = st.session_state.session_results

    spoken_correct_count = sum(1 for r in results if r["spoken_correct"])
    knowledge_correct_count = sum(1 for r in results if r["knowledge_correct"])
    missed_count = sum(1 for r in results if not r["knowledge_correct"])
    review_count = sum(1 for r in results if r["review_type"] != "none")

    total_count = len(results)

    spoken_score = round((spoken_correct_count / total_count) * 100, 1) if total_count else 0
    knowledge_score = round((knowledge_correct_count / total_count) * 100, 1) if total_count else 0

    st.header("Test Complete")

    st.metric("Spoken Score", f"{spoken_correct_count}/{total_count} — {spoken_score}%")
    st.metric("Knowledge Score", f"{knowledge_correct_count}/{total_count} — {knowledge_score}%")
    st.metric("Needs Review", review_count)
    st.metric("Missed", missed_count)

    if total_count == 20 and knowledge_correct_count >= PASSING_SCORE:
        st.success("Passing pace on knowledge. Now focus on clear spoken delivery.")
    else:
        st.warning("Good practice session. Review missed questions and pronunciation/transcription flags.")

    st.subheader("Review")

    for i, result in enumerate(results, start=1):
        q = result["question"]

        if result["spoken_correct"]:
            st.write(f"✅ **{i}. {q['question']}**")
            st.write(f"Voice answer accepted: {result['selected']}")

        elif result["knowledge_correct"]:
            st.write(f"🟡 **{i}. {q['question']}**")
            st.write("Knowledge correct after multiple choice.")
            st.write(f"Multiple choice answer: {result['multiple_choice_answer']}")
            st.write("Review flag: pronunciation/transcription/system check")

        else:
            st.write(f"❌ **{i}. {q['question']}**")
            st.write("Missed after spoken attempts and multiple choice.")
            st.write("Accepted answer(s):")
            for answer in q["answers"]:
                st.write(f"- {answer}")

        if result.get("attempts"):
            st.caption("Spoken attempt log:")
            for attempt in result["attempts"]:
                st.caption(
                    f"Attempt {attempt['attempt_number']}: "
                    f"'{attempt['transcript']}' | "
                    f"best match: {attempt['best_answer']} | "
                    f"score: {attempt['score']}"
                )

        st.divider()

    if st.button("Take Another Test"):
        start_new_session(mode, questions, special_only)
        st.rerun()

    st.stop()


# -----------------------------
# Active question screen
# -----------------------------

question = current_question()
question_number = st.session_state.current_index + 1
total_questions = len(st.session_state.session_questions)

st.subheader(f"Question {question_number} of {total_questions}")
st.write(f"**Category:** {question['category']}")

active_voice = st.session_state.get("interviewer_voice", INTERVIEWER_VOICES[0])
st.caption(f"Active interviewer voice: {active_voice['label']}")

st.markdown(f"### {question['question']}")

if not st.session_state.get("started", False):
    if st.button("Begin"):
        st.session_state.started = True
        speak_text_mac(question["question"], active_voice["name"])
        st.session_state.spoken_index = st.session_state.current_index
        st.rerun()

else:
    if st.session_state.get("spoken_index") != st.session_state.current_index:
        speak_text_mac(question["question"], active_voice["name"])
        st.session_state.spoken_index = st.session_state.current_index

    if st.button("Repeat Question"):
        speak_text_mac(question["question"], active_voice["name"])


st.markdown("### Spoken Answer")
st.caption("Record the answer. The app will use the voice transcript as the official submitted answer.")

if sr is None:
    st.error("SpeechRecognition package is not installed. Run: python3 -m pip install SpeechRecognition")


if not st.session_state.revealed:
    recorded_answer = st.audio_input("Record answer", key=st.session_state.answer_widget_key)

    if recorded_answer is not None:
        with st.spinner("Transcribing answer..."):
            transcript, error = transcribe_audio(recorded_answer)

        if error:
            st.warning(f"Automatic transcription issue: {error}")
            st.session_state.transcript = ""
        else:
            st.session_state.transcript = transcript
            st.success("Transcript captured.")

        st.audio(recorded_answer)

    st.text_area(
        "Transcript captured from voice:",
        value=st.session_state.get("transcript", ""),
        disabled=True,
        height=90,
    )

    if st.button("Submit Spoken Answer", disabled=st.session_state.submitted):
        transcript = st.session_state.get("transcript", "").strip()

        if not transcript:
            st.warning("Record the answer first.")
        else:
            validation = validate_spoken_answer(transcript, question["answers"])
            st.session_state.last_validation = validation

            st.session_state.spoken_attempts += 1

            st.session_state.attempt_log.append(
                {
                    "attempt_number": st.session_state.spoken_attempts,
                    "transcript": transcript,
                    "correct": validation["correct"],
                    "close": validation["close"],
                    "best_answer": validation["best_answer"],
                    "score": validation["score"],
                    "timestamp": datetime.now().isoformat(),
                }
            )

            if validation["correct"]:
                progress = load_progress()
                update_question(progress, question["id"], "spoken_correct")

                st.session_state.session_results.append(
                    build_result_record(
                        question=question,
                        final_result="spoken_correct",
                        final_answer=transcript,
                    )
                )

                st.session_state.submitted = True
                move_to_next_question()
                st.rerun()

            if st.session_state.spoken_attempts < MAX_SPOKEN_ATTEMPTS:
                st.warning("Not quite. Let’s try that same question one more time.")

                if validation["close"]:
                    st.info("That sounded close. We may need pronunciation/transcription review later.")

                reset_question_state_for_retry()
                st.rerun()

            else:
                st.session_state.submitted = True
                st.session_state.revealed = True
                st.rerun()


# -----------------------------
# Multiple choice remediation
# -----------------------------

if st.session_state.revealed:
    st.markdown("### Knowledge Check")
    st.caption("Spoken answer was not accepted. Choose the best answer so we can separate knowledge from pronunciation/transcription.")

    if st.session_state.get("current_choices") is None:
        st.session_state.current_choices = make_choices(question, questions)

    selected_choice = st.radio(
        "Choose the best answer:",
        st.session_state.current_choices,
        index=None,
        key=st.session_state.choice_widget_key,
    )

    if st.button("Submit Multiple Choice"):
        if selected_choice is None:
            st.warning("Choose an answer first.")

        elif is_correct_choice(selected_choice, question["answers"]):
            progress = load_progress()
            update_question(progress, question["id"], "knowledge_correct")

            st.session_state.session_results.append(
                build_result_record(
                    question=question,
                    final_result="knowledge_correct",
                    mc_answer=selected_choice,
                )
            )

            st.success("Correct. Knowledge is there. Flagged for pronunciation/transcription review.")
            move_to_next_question()
            st.rerun()

        else:
            progress = load_progress()
            update_question(progress, question["id"], "missed")

            st.session_state.session_results.append(
                build_result_record(
                    question=question,
                    final_result="missed",
                    mc_answer=selected_choice,
                )
            )

            st.error("Still not quite. Review the correct answer below.")

            st.markdown("#### Accepted answer(s)")
            for answer in question["answers"]:
                st.write(f"- {answer}")

            st.markdown("#### Coach note")
            st.success(random.choice(CONFIDENCE_MESSAGES))

            if st.button("Continue"):
                move_to_next_question()
                st.rerun()
