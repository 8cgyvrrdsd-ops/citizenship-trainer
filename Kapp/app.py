import json
import random
import re
import subprocess
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path
from datetime import datetime

import streamlit as st

try:
    import speech_recognition as sr
except ImportError:
    sr = None

APP_TITLE = "Ket's Citizenship Trainer"
def existing_path(*paths):
    for path in paths:
        if path.exists():
            return path
    return paths[0]

QUESTIONS_FILE = existing_path(Path("questions.json"), Path("data/questions.json"))
QUESTIONS_HARD_FILE = existing_path(Path("questions_hard.json"), Path("data/questions_hard.json"))
QA_QUESTIONS_FILE = existing_path(Path("questions_multi_answer_QA.json"), Path("data/questions_multi_answer_QA.json"))
PROGRESS_FILE = existing_path(Path("progress.json"), Path("data/progress.json"))
DYNAMIC_ANSWERS_FILE = existing_path(Path("dynamic_answers.json"), Path("data/dynamic_answers.json"))

SESSION_LENGTH = 20
PASSING_SCORE = 12
MAX_SPOKEN_ATTEMPTS = 2
VOICE_FEEDBACK_PAUSE_SECONDS = 1.4

# Prevents the app from treating recorder-start noise/empty audio as a failed answer.
MIN_AUDIO_BYTES_TO_PROCESS = 5000

# QA mode: set to False when ready to use questions.json again
USE_TEST_QUESTIONS = False

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

    if st.session_state.get("use_qa_questions", False):
        if QA_QUESTIONS_FILE.exists():
            return json.loads(QA_QUESTIONS_FILE.read_text(encoding="utf-8"))
        st.warning("QA Sandbox Mode is ON, but questions_multi_answer_QA.json was not found.")

    active_file = QUESTIONS_HARD_FILE if st.session_state.get("civics_difficulty", "Easy") == "Hard" else QUESTIONS_FILE

    if active_file.exists():
        return json.loads(active_file.read_text(encoding="utf-8"))

    return FALLBACK_QUESTIONS


def load_dynamic_answers():
    if DYNAMIC_ANSWERS_FILE.exists():
        return json.loads(DYNAMIC_ANSWERS_FILE.read_text(encoding="utf-8"))
    return {"dynamic_answers": {}}


def get_dynamic_entry(dynamic_data, key):
    return dynamic_data.get("dynamic_answers", {}).get(key, {})


def apply_dynamic_answer(question, dynamic_data, key):
    entry = get_dynamic_entry(dynamic_data, key)
    answers = entry.get("answers", [])
    choices = entry.get("choices", [])

    if answers:
        question["answers"] = answers
        question["dynamic_answer"] = True
        question["dynamic_key"] = key

    if choices:
        question["choices"] = choices

    return question


def apply_question_overrides(questions, dynamic_data=None):
    """
    Runtime cleanup.

    Keeps questions.json mostly static while dynamic_answers.json supplies:
      - current officeholders
      - Indiana-specific answers
      - clean multiple-choice options
    """
    dynamic_data = dynamic_data or {"dynamic_answers": {}}

    for q in questions:
        q_text = q.get("question", "").lower()

        if "speaker of the house" in q_text:
            apply_dynamic_answer(q, dynamic_data, "speaker_of_the_house")

        elif "president of the united states now" in q_text or "president now" in q_text:
            apply_dynamic_answer(q, dynamic_data, "president")

        elif "vice president of the united states now" in q_text or "vice president now" in q_text:
            apply_dynamic_answer(q, dynamic_data, "vice_president")

        elif "chief justice of the united states" in q_text:
            apply_dynamic_answer(q, dynamic_data, "chief_justice")

        elif "governor of your state" in q_text:
            apply_dynamic_answer(q, dynamic_data, "governor_indiana")

        elif "capital of your state" in q_text:
            apply_dynamic_answer(q, dynamic_data, "capital_indiana")

        elif "one of your state" in q_text and "u.s. senators" in q_text:
            apply_dynamic_answer(q, dynamic_data, "senators_indiana")

        elif "name your u.s. representative" in q_text:
            apply_dynamic_answer(q, dynamic_data, "representative_in09")

        elif q.get("answers"):
            # Clean copy/paste artifacts inside regular answer lists.
            cleaned_answers = []
            for answer in q["answers"]:
                cleaned = clean_answer(answer)

                # Remove instructional junk from answers.
                if is_bad_choice_text(cleaned):
                    continue

                # Specific cleanup for tribe question artifact:
                cleaned = cleaned.replace("Tuscarora For a complete list of tribes, please visit bia.gov.", "Tuscarora")

                if cleaned:
                    cleaned_answers.append(cleaned)

            if cleaned_answers:
                q["answers"] = list(dict.fromkeys(cleaned_answers))

    return questions


def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {"questions": {}, "sessions": [], "created_at": datetime.now().isoformat()}


def save_progress(progress):
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2), encoding="utf-8")


def make_json_safe_result(result):
    """
    Keeps saved session history clean and JSON-friendly.
    """
    return {
        "question_id": result.get("question", {}).get("id"),
        "question_text": result.get("question", {}).get("question"),
        "category": result.get("question", {}).get("category"),
        "accepted_answers": result.get("question", {}).get("answers", []),
        "final_result": result.get("final_result"),
        "correct": result.get("correct"),
        "spoken_correct": result.get("spoken_correct"),
        "knowledge_correct": result.get("knowledge_correct"),
        "multiple_choice_used": result.get("multiple_choice_used"),
        "selected": result.get("selected"),
        "multiple_choice_answer": result.get("multiple_choice_answer"),
        "attempts": result.get("attempts", []),
        "attempt_count": result.get("attempt_count", 0),
        "best_match": result.get("best_match", ""),
        "best_score": result.get("best_score", 0),
        "review_type": result.get("review_type", ""),
        "timestamp": result.get("timestamp"),
    }


def save_completed_session(results):
    """
    Saves the finished test into progress.json so multiple tests can be summarized together.
    """
    progress = load_progress()
    progress.setdefault("sessions", [])

    safe_results = [make_json_safe_result(r) for r in results]

    total = len(safe_results)
    spoken_correct = sum(1 for r in safe_results if r.get("spoken_correct"))
    knowledge_correct = sum(1 for r in safe_results if r.get("knowledge_correct"))
    missed = sum(1 for r in safe_results if not r.get("knowledge_correct"))
    review_needed = sum(1 for r in safe_results if r.get("review_type") != "none")

    session_record = {
        "completed_at": datetime.now().isoformat(),
        "total_questions": total,
        "spoken_correct": spoken_correct,
        "knowledge_correct": knowledge_correct,
        "missed": missed,
        "review_needed": review_needed,
        "spoken_score_percent": round((spoken_correct / total) * 100, 1) if total else 0,
        "knowledge_score_percent": round((knowledge_correct / total) * 100, 1) if total else 0,
        "results": safe_results,
    }

    progress["sessions"].append(session_record)
    save_progress(progress)


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
    st.session_state.session_saved = False

    st.session_state.interviewer_voice = random.choice(INTERVIEWER_VOICES)


def current_question():
    return st.session_state.session_questions[st.session_state.current_index]


def reset_question_state_for_retry():
    st.session_state.transcript = ""
    st.session_state.answer_widget_key = fresh_answer_key()

    # Do NOT reset spoken_index here.
    # If we reset it, the app automatically re-reads the same question after a missed attempt.
    # User can use the "Repeat Question" button when they want to hear it again.


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

def speak_text_mac(text, voice_name=None, wait=False):
    try:
        command = ["say"]
        if voice_name:
            command.extend(["-v", voice_name])
        command.append(text)

        if wait:
            subprocess.run(command)
        else:
            subprocess.Popen(command)

        return True
    except Exception:
        return False


def speak_feedback_then_pause(message, voice_name=None):
    speak_text_mac(message, voice_name, wait=True)
    time.sleep(VOICE_FEEDBACK_PAUSE_SECONDS)


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


def is_bad_choice_text(text):
    """
    Filters out study-guide placeholders and unusable answer text.
    """
    if not text:
        return True

    lowered = text.lower()

    bad_phrases = [
        "visit uscis.gov",
        "uscis.gov/citizenship/testupdates",
        "answers will vary",
        "answer will vary",
        "varies",
        "see uscis",
        "check uscis",
        "go to uscis",
        "for a complete list",
    ]

    return any(phrase in lowered for phrase in bad_phrases)


def normalize_text(text):
    text = text.lower()
    text = text.replace("u.s.", "us").replace("united states", "us")
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def score_answer_match(spoken, expected):
    """
    Scores how well one expected answer appears in the spoken transcript.
    """
    expected = normalize_text(clean_answer(expected))

    if not spoken or not expected:
        return 0

    if expected in spoken:
        return 1.0

    spoken_words = set(spoken.split())
    expected_words = set(expected.split())

    overlap = len(spoken_words & expected_words) / max(1, len(expected_words))
    similarity = SequenceMatcher(None, spoken, expected).ratio()

    return max(overlap, similarity)


def validate_spoken_answer(transcript, question_or_answers):
    """
    Validates a spoken answer.

    Supports single-answer and multi-answer questions using required_count.
    """
    spoken = normalize_text(transcript)

    if isinstance(question_or_answers, dict):
        accepted_answers = question_or_answers.get("answers", [])
        required_count = int(question_or_answers.get("required_count", 1) or 1)
        aliases = question_or_answers.get("aliases", [])
    else:
        accepted_answers = question_or_answers
        required_count = 1
        aliases = []

    all_expected = list(accepted_answers) + list(aliases)

    if not spoken:
        return {
            "correct": False,
            "close": False,
            "best_answer": "",
            "score": 0,
            "required_count": required_count,
            "matched_answers": [],
            "matched_count": 0,
            "missing_count": required_count,
            "partial": False,
        }

    matches = []
    best_answer = ""
    best_score = 0

    for answer in all_expected:
        expected_clean = clean_answer(answer)
        expected_norm = normalize_text(expected_clean)

        if not expected_norm:
            continue

        score = score_answer_match(spoken, expected_clean)

        if score > best_score:
            best_score = score
            best_answer = expected_clean

        item_matched = (
            expected_norm in spoken
            or score >= 0.78
            or (
                len(expected_norm.split()) == 1
                and expected_norm in set(spoken.split())
            )
        )

        if item_matched:
            matches.append(expected_clean)

    unique_matches = []
    seen_norms = set()
    for match in matches:
        norm = normalize_text(match)
        if norm not in seen_norms:
            unique_matches.append(match)
            seen_norms.add(norm)

    matched_count = len(unique_matches)
    correct = matched_count >= required_count
    close = (
        (not correct and best_score >= 0.55)
        or (required_count > 1 and matched_count > 0)
    )

    return {
        "correct": correct,
        "close": close,
        "best_answer": best_answer,
        "score": round(best_score, 2),
        "required_count": required_count,
        "matched_answers": unique_matches,
        "matched_count": matched_count,
        "missing_count": max(0, required_count - matched_count),
        "partial": required_count > 1 and matched_count > 0 and not correct,
    }


def make_multi_answer_choice_combos(question):
    """
    For required_count questions, build normal radio-button answer combos:
    A) correct + correct
    B) correct + wrong
    C) wrong + wrong
    D) another correct mix when possible

    This is easier for users than a multiselect dropdown.
    """
    required_count = int(question.get("required_count", 1) or 1)
    correct_pool = [clean_answer(a) for a in question.get("answers", []) if clean_answer(a)]
    wrong_pool = [clean_answer(c) for c in question.get("choices", []) if clean_answer(c)]

    # Remove correct answers from wrong pool.
    correct_norms = {normalize_text(a) for a in correct_pool}
    wrong_pool = [
        w for w in wrong_pool
        if normalize_text(w) not in correct_norms
    ]

    # Add generic wrong choices if not enough exist.
    fallback_wrong = [
        "Green",
        "Purple",
        "Halloween",
        "Valentine's Day",
        "Chief Justice",
        "Speaker of the House",
        "Civil War",
        "World War II",
        "New York City",
        "Philadelphia",
    ]
    for wrong in fallback_wrong:
        if normalize_text(wrong) not in correct_norms and wrong not in wrong_pool:
            wrong_pool.append(wrong)

    combos = []

    # Correct combo
    if len(correct_pool) >= required_count:
        combos.append(correct_pool[:required_count])

    # Mixed/wrong combos
    if correct_pool and wrong_pool:
        combos.append((correct_pool[:max(1, required_count - 1)] + wrong_pool[:1])[:required_count])

    if len(wrong_pool) >= required_count:
        combos.append(wrong_pool[:required_count])

    if len(correct_pool) >= required_count + 1 and wrong_pool:
        combos.append((correct_pool[1:required_count] + wrong_pool[1:2])[:required_count])

    # Pad if needed.
    while len(combos) < 4:
        start = len(combos)
        combo = []
        for i in range(required_count):
            pool = wrong_pool if start % 2 else correct_pool
            if pool:
                combo.append(pool[(start + i) % len(pool)])
        if combo:
            combos.append(combo)
        else:
            break

    # Deduplicate combo labels.
    final = []
    seen = set()
    for combo in combos:
        combo = combo[:required_count]
        label = " and ".join(combo) if len(combo) == 2 else ", ".join(combo)
        norm = normalize_text(label)
        if norm not in seen:
            final.append(label)
            seen.add(norm)

    random.shuffle(final)
    return final[:4]


def is_correct_multi_combo(selected_combo, question):
    """
    Checks whether a radio-button combo contains enough correct answers.
    """
    required_count = int(question.get("required_count", 1) or 1)

    if not selected_combo:
        return False

    selected_norm = normalize_text(selected_combo)
    matched = []

    for answer in question.get("answers", []):
        answer_clean = clean_answer(answer)
        answer_norm = normalize_text(answer_clean)

        if not answer_norm:
            continue

        if answer_norm in selected_norm:
            matched.append(answer_norm)

    return len(set(matched)) >= required_count


def make_choices(question, all_questions):
    """
    Builds multiple choice options.

    Priority:
    1. If the question has a clean "choices" list in questions.json, use it.
    2. Otherwise, generate choices from other answers but filter out placeholders.
    """
    if question.get("choices"):
        clean_choices = []
        for choice in question["choices"]:
            choice = clean_answer(choice)
            if choice and not is_bad_choice_text(choice):
                clean_choices.append(choice)

        # Remove duplicates while preserving order.
        clean_choices = list(dict.fromkeys(clean_choices))
        random.shuffle(clean_choices)
        return clean_choices

    accepted_answers = [
        clean_answer(answer)
        for answer in question.get("answers", [])
        if clean_answer(answer) and not is_bad_choice_text(clean_answer(answer))
    ]

    correct_answer = accepted_answers[0] if accepted_answers else clean_answer(question["answers"][0])

    wrong_pool = []

    for q in all_questions:
        if q["id"] == question["id"] or not q.get("answers"):
            continue

        candidate = clean_answer(q["answers"][0])

        if (
            candidate
            and not is_bad_choice_text(candidate)
            and candidate.lower() != correct_answer.lower()
            and len(candidate) <= 80
        ):
            wrong_pool.append(candidate)

    wrong_pool = list(dict.fromkeys(wrong_pool))
    random.shuffle(wrong_pool)

    choices = [correct_answer] + wrong_pool[:3]
    choices = [choice for choice in choices if choice and not is_bad_choice_text(choice)]
    choices = list(dict.fromkeys(choices))

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


def process_spoken_submission(question):
    """
    Auto-submits the captured transcript after recording stops.
    """
    transcript = st.session_state.get("transcript", "").strip()

    if not transcript:
        st.warning("Record the answer first.")
        return

    validation = validate_spoken_answer(transcript, question)
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
            "required_count": validation.get("required_count", 1),
            "matched_answers": validation.get("matched_answers", []),
            "matched_count": validation.get("matched_count", 0),
            "missing_count": validation.get("missing_count", 0),
            "partial": validation.get("partial", False),
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

        if st.session_state.current_index + 1 >= len(st.session_state.session_questions):
            speak_feedback_then_pause(
                "Excellent work. You have completed the USCIS practice exam.",
                st.session_state.get("interviewer_voice", {}).get("name")
            )
        else:
            speak_feedback_then_pause(
                "Correct. Next question.",
                st.session_state.get("interviewer_voice", {}).get("name")
            )

        move_to_next_question()
        st.rerun()

    if st.session_state.spoken_attempts < MAX_SPOKEN_ATTEMPTS:
        if validation.get("partial"):
            st.warning(
                f"You gave {validation.get('matched_count', 0)} correct answer(s). "
                f"This question needs {validation.get('required_count', 1)}. Try again."
            )
            if validation.get("matched_answers"):
                st.info("Matched: " + ", ".join(validation["matched_answers"]))
            speak_feedback_then_pause(
                "You gave a partial answer. Try again.",
                st.session_state.get("interviewer_voice", {}).get("name")
            )
        else:
            st.caption("Retry the same question.")
        speak_feedback_then_pause("Not quite. Try again.", st.session_state.get("interviewer_voice", {}).get("name"))

        if validation["close"]:
            st.info("That sounded close. We may need pronunciation/transcription review later.")

        reset_question_state_for_retry()
        st.rerun()

    else:
        st.session_state.submitted = True
        st.session_state.revealed = True
        st.rerun()




# -----------------------------
# N-400 practice module
# -----------------------------

# Personal N-400 answer bank for Ket. Keep short answer variants here.
# These are used by the same voice/transcript matcher as the civics trainer.
N400_PROFILE = {
    "full_name": ["Ketmanee Utsa", "Ketmanee"],
    "date_of_birth": ["April 9 1980", "April ninth nineteen eighty", "April 9th 1980", "4 9 1980"],
    "country_of_birth": ["Thailand"],
    "current_address": [
        "1710 Charlestown New Albany Road Jeffersonville Indiana 47130",
        "1710 Charlestown New Albany Road Jeffersonville IN 47130",
        "1710 Charlestown New Albany Road",
    ],
    "prior_address": [
        "210 Ettels Lane Clarksville Indiana 47129",
        "210 Ettels Lane Clarksville IN 47129",
        "210 Ettels Lane",
    ],
    "occupation": ["Kitchen Work", "Kitchen worker", "Kitchen"],
    "employer": ["Panda Express"],
    "employment_combined": ["Kitchen Work at Panda Express", "Kitchen worker at Panda Express", "Panda Express"],
    "marital_status": ["Married"],
    "spouse_name": ["Joseph Worth", "Joseph", "Joseph Karl Worth"],
    "children": ["No", "No children", "I do not have children"],
    "travel": ["Yes", "Yes I have", "Yes I traveled outside the United States"],
}

N400_INTERVIEW_QUESTIONS = [
    {"id": "n400_name_1", "topic": "Name", "question": "What is your full legal name?", "answers": N400_PROFILE["full_name"]},
    {"id": "n400_birth_1", "topic": "Birth", "question": "What is your date of birth?", "answers": N400_PROFILE["date_of_birth"]},
    {"id": "n400_birth_2", "topic": "Birth", "question": "What is your country of birth?", "answers": N400_PROFILE["country_of_birth"]},
    {"id": "n400_address_1", "topic": "Address", "question": "What is your current home address?", "answers": N400_PROFILE["current_address"]},
    {"id": "n400_address_2", "topic": "Address", "question": "Where did you live before your current address?", "answers": N400_PROFILE["prior_address"]},
    {"id": "n400_work_1", "topic": "Employment", "question": "What is your occupation?", "answers": N400_PROFILE["occupation"]},
    {"id": "n400_work_2", "topic": "Employment", "question": "Where do you work?", "answers": N400_PROFILE["employer"]},
    {"id": "n400_work_3", "topic": "Employment", "question": "What kind of work do you do at Panda Express?", "answers": N400_PROFILE["occupation"]},
    {"id": "n400_family_1", "topic": "Family", "question": "What is your marital status?", "answers": N400_PROFILE["marital_status"]},
    {"id": "n400_family_2", "topic": "Family", "question": "What is your spouse's name?", "answers": N400_PROFILE["spouse_name"]},
    {"id": "n400_family_3", "topic": "Family", "question": "Do you have any children?", "answers": N400_PROFILE["children"]},
    {"id": "n400_travel_1", "topic": "Travel", "question": "Have you traveled outside the United States in the past five years?", "answers": N400_PROFILE["travel"]},
]

N400_SELF_TEST_1 = [
    {"passage": "The employee's name is Mr. John David Fenton.", "question": "What is his first name?", "options": ["Mr.", "John", "David"], "answer": "John"},
    {"passage": "The employee's name is Mr. John David Fenton.", "question": "What is his family name?", "options": ["Mr.", "Fenton", "John"], "answer": "Fenton"},
    {"passage": "The employee's name is Mr. John David Fenton.", "question": "What is his middle name?", "options": ["Mr.", "John", "David"], "answer": "David"},
    {"passage": "Bill was born in Australia and now lives in Chicago, Illinois. His address is 220 Cedar Street, Apt. B1, Chicago, Illinois 60603.", "question": "What is Bill's country of birth?", "options": ["Australia", "Illinois", "United States"], "answer": "Australia"},
    {"passage": "Bill was born in Australia and now lives in Chicago, Illinois. His address is 220 Cedar Street, Apt. B1, Chicago, Illinois 60603.", "question": "Where does Bill currently live?", "options": ["Texas", "Australia", "Chicago"], "answer": "Chicago"},
    {"passage": "Bill was born in Australia and now lives in Chicago, Illinois. His address is 220 Cedar Street, Apt. B1, Chicago, Illinois 60603.", "question": "What is Bill's apartment number?", "options": ["B1", "60603", "220"], "answer": "B1"},
    {"passage": "Bill was born in Australia and now lives in Chicago, Illinois. His address is 220 Cedar Street, Apt. B1, Chicago, Illinois 60603.", "question": "What is Bill's zip code?", "options": ["220", "60603", "B1"], "answer": "60603"},
    {"passage": "Tom works as a doctor at Mount Carmel Hospital. He has worked there for two years.", "question": "What is the name of Tom's employer?", "options": ["a hospital", "a doctor", "Mount Carmel Hospital"], "answer": "Mount Carmel Hospital"},
    {"passage": "Tom works as a doctor at Mount Carmel Hospital. He has worked there for two years.", "question": "What is Tom's occupation?", "options": ["a doctor", "two years", "Mount Carmel Hospital"], "answer": "a doctor"},
    {"passage": "Donna has one son and one daughter. Her spouse died last year.", "question": "How many children does Donna have?", "options": ["1", "2", "3"], "answer": "2"},
    {"passage": "Donna has one son and one daughter. Her spouse died last year.", "question": "What is Donna's marital status?", "options": ["separated", "widowed", "divorced"], "answer": "widowed"},
    {"passage": "Mary currently lives in Philadelphia, Pennsylvania. Prior to that, she lived for three years in Miami, Florida.", "question": "Where does Mary live now?", "options": ["Philadelphia", "Miami", "Los Angeles"], "answer": "Philadelphia"},
    {"passage": "Mary currently lives in Philadelphia, Pennsylvania. Prior to that, she lived for three years in Miami, Florida.", "question": "Where did Mary live before Philadelphia?", "options": ["New York", "Pennsylvania", "Miami"], "answer": "Miami"},
    {"passage": "Susan takes two trips each year. She visits her parents in Paris, France, for three weeks every summer. She also visits her brother in Mexico City, Mexico, for one week each December.", "question": "How much time does Susan spend outside of the United States during these two trips each year?", "options": ["one year", "three weeks", "four weeks"], "answer": "four weeks"},
    {"passage": "Susan takes two trips each year. She visits her parents in Paris, France, for three weeks every summer. She also visits her brother in Mexico City, Mexico, for one week each December.", "question": "How many trips outside of the United States does Susan take each year?", "options": ["one trip", "two trips", "three trips"], "answer": "two trips"},
    {"passage": "Susan takes two trips each year. She visits her parents in Paris, France, for three weeks every summer. She also visits her brother in Mexico City, Mexico, for one week each December.", "question": "Which two countries does Susan travel to each year?", "options": ["France and Mexico", "Canada and Mexico", "France and Japan"], "answer": "France and Mexico"},
    {"passage": "Lisa is 5 feet 7 inches tall. She is 27 years old. She has blonde hair and green eyes.", "question": "What is Lisa's age?", "options": ["5 feet 7 inches", "27", "green"], "answer": "27"},
    {"passage": "Lisa is 5 feet 7 inches tall. She is 27 years old. She has blonde hair and green eyes.", "question": "What is Lisa's height?", "options": ["blonde", "27", "5 feet 7 inches"], "answer": "5 feet 7 inches"},
]

N400_VOCAB_QUESTIONS = [
    {"word": "verify", "meaning": "prove something is true", "question": "Can you verify your current home address?", "answers": ["Yes", "Yes I can", "Yes here is my driver's license", "Yes here is my ID"]},
    {"word": "marital status", "meaning": "whether you are married, divorced, single, or widowed", "question": "What is your marital status?", "answers": N400_PROFILE["marital_status"]},
    {"word": "spouse", "meaning": "husband or wife", "question": "What is your spouse's name?", "answers": N400_PROFILE["spouse_name"]},
    {"word": "current home address", "meaning": "where you live now", "question": "What is your current home address?", "answers": N400_PROFILE["current_address"]},
    {"word": "date of birth", "meaning": "when you were born", "question": "What is your date of birth?", "answers": N400_PROFILE["date_of_birth"]},
    {"word": "prior", "meaning": "before", "question": "Where did you live prior to your current address?", "answers": N400_PROFILE["prior_address"]},
    {"word": "resident", "meaning": "someone who lives in a place", "question": "Are you a resident of Indiana?", "answers": ["Yes", "Yes I am", "Yes I live in Indiana"]},
    {"word": "dependents", "meaning": "people you support financially", "question": "Do you have any dependents?", "answers": ["No", "No dependents", "No I do not"]},
    {"word": "pending", "meaning": "not decided yet", "question": "Do you have any pending immigration applications?", "answers": ["No", "No I do not"]},
    {"word": "swear", "meaning": "promise", "question": "Do you swear to tell the truth?", "answers": ["Yes", "Yes I do", "I do"]},
    {"word": "failed to", "meaning": "did not do something", "question": "Have you ever failed to file your taxes?", "answers": ["No", "No I have not"]},
    {"word": "federal", "meaning": "U.S. government", "question": "Have you ever owed federal taxes?", "answers": ["No", "No I have not"]},
    {"word": "requested", "meaning": "asked for", "question": "Have you ever requested an immigration benefit for someone else?", "answers": ["No", "No I have not"]},
]

N400_READING_SENTENCES = [
    "Who was George Washington?",
    "George Washington was the Father of Our Country.",
    "Abraham Lincoln was President.",
    "The President lives in the White House.",
    "Congress makes laws.",
    "Citizens can vote.",
    "We pay taxes.",
    "The United States has fifty states.",
    "Independence Day is in July.",
    "Thanksgiving is in November.",
    "What is the capital of the United States?",
    "Where is the White House?",
]



def reset_n400_flow_state():
    """Reset only the active N-400 practice flow."""
    for key in [
        "n400_flow_section",
        "n400_flow_index",
        "n400_flow_started",
        "n400_flow_finished",
        "n400_flow_attempts",
        "n400_flow_transcript",
        "n400_flow_revealed",
        "n400_flow_spoken_index",
        "n400_flow_results",
        "n400_flow_voice_key",
        "n400_flow_choice_key",
        "n400_flow_last_validation",
        "n400_flow_show_answer",
    ]:
        st.session_state.pop(key, None)


def start_n400_flow(section):
    st.session_state.n400_flow_section = section
    st.session_state.n400_flow_index = 0
    st.session_state.n400_flow_started = False
    st.session_state.n400_flow_finished = False
    st.session_state.n400_flow_attempts = 0
    st.session_state.n400_flow_transcript = ""
    st.session_state.n400_flow_revealed = False
    st.session_state.n400_flow_spoken_index = None
    st.session_state.n400_flow_results = []
    st.session_state.n400_flow_voice_key = fresh_answer_key()
    st.session_state.n400_flow_choice_key = fresh_choice_key()
    st.session_state.n400_flow_last_validation = None
    st.session_state.n400_flow_show_answer = False


def get_n400_bank(section):
    if section == "Personal Interview":
        return N400_INTERVIEW_QUESTIONS
    if section == "Vocabulary Interview":
        return N400_VOCAB_QUESTIONS
    if section == "Reading Practice":
        return [
            {
                "id": f"reading_{i}",
                "topic": "Reading",
                "question": sentence,
                "answers": [sentence],
                "sentence": sentence,
            }
            for i, sentence in enumerate(N400_READING_SENTENCES, start=1)
        ]
    return []


def prepare_n400_item(item, section):
    """Return one normalized item for the shared N-400 voice workflow."""
    if section == "Vocabulary Interview":
        return {
            "id": item.get("word", item.get("id", "vocab")),
            "topic": f"Vocabulary: {item['word']}",
            "question": item["question"],
            "answers": item.get("answers", []),
            "study_note": f"Meaning: {item.get('meaning', '')}",
        }

    if section == "Reading Practice":
        return {
            "id": item.get("id", "reading"),
            "topic": "Reading Test Practice",
            "question": item.get("sentence", item.get("question", "")),
            "answers": item.get("answers", []),
            "study_note": "Read the displayed sentence aloud. This checks reading, not personal interview answers.",
        }

    return {
        "id": item.get("id", "n400"),
        "topic": item.get("topic", "N-400"),
        "question": item.get("question", ""),
        "answers": item.get("answers", []),
        "study_note": "Answer out loud. The app transcribes and checks the spoken answer automatically.",
    }


def reset_n400_question_state():
    st.session_state.n400_flow_attempts = 0
    st.session_state.n400_flow_transcript = ""
    st.session_state.n400_flow_revealed = False
    st.session_state.n400_flow_voice_key = fresh_answer_key()
    st.session_state.n400_flow_choice_key = fresh_choice_key()
    st.session_state.n400_flow_last_validation = None
    st.session_state.n400_flow_show_answer = False


def move_to_next_n400_question(section):
    bank = get_n400_bank(section)
    st.session_state.n400_flow_index += 1
    reset_n400_question_state()

    if st.session_state.n400_flow_index >= len(bank):
        st.session_state.n400_flow_finished = True


def make_n400_choice_options(expected_answers):
    correct_answer = next((a for a in expected_answers if a), "Yes")

    wrong_pool = [
        "No",
        "Yes",
        "I do not know",
        "New York",
        "California",
        "Florida",
        "Single",
        "Divorced",
        "Widowed",
        "Student",
        "Hospital",
        "Two children",
        "No children",
        "United States",
    ]

    expected_norms = {normalize_text(a) for a in expected_answers}
    choices = [correct_answer]

    for wrong in wrong_pool:
        if normalize_text(wrong) not in expected_norms and wrong not in choices:
            choices.append(wrong)
        if len(choices) >= 4:
            break

    random.shuffle(choices)
    return choices


def record_n400_result(item, final_result, selected=""):
    validation = st.session_state.get("n400_flow_last_validation") or {}
    st.session_state.n400_flow_results.append(
        {
            "id": item.get("id"),
            "topic": item.get("topic"),
            "question": item.get("question"),
            "answers": item.get("answers", []),
            "final_result": final_result,
            "selected": selected,
            "transcript": st.session_state.get("n400_flow_transcript", ""),
            "attempts": st.session_state.get("n400_flow_attempts", 0),
            "best_match": validation.get("best_answer", ""),
            "best_score": validation.get("score", 0),
            "timestamp": datetime.now().isoformat(),
        }
    )


def process_n400_recording(recorded_answer, item, section):
    if recorded_answer is None:
        return

    audio_bytes = recorded_answer.getvalue()
    audio_size = len(audio_bytes) if audio_bytes else 0

    if audio_size < MIN_AUDIO_BYTES_TO_PROCESS:
        st.info("Recording... stop the recorder when finished.")
        return

    with st.spinner("Transcribing and checking answer..."):
        transcript, error = transcribe_audio(recorded_answer)

    if error or not transcript.strip():
        st.warning("I did not catch that clearly. Try again.")
        speak_feedback_then_pause(
            "I did not catch that. Try again.",
            st.session_state.get("interviewer_voice", {}).get("name"),
        )
        st.session_state.n400_flow_transcript = ""
        st.session_state.n400_flow_voice_key = fresh_answer_key()
        st.rerun()

    st.session_state.n400_flow_transcript = transcript
    validation = validate_spoken_answer(transcript, {"answers": item.get("answers", [])})
    st.session_state.n400_flow_last_validation = validation
    st.session_state.n400_flow_attempts += 1

    st.success(f"Transcript captured: {transcript}")

    if validation["correct"]:
        record_n400_result(item, "spoken_correct", transcript)
        speak_feedback_then_pause(
            "Correct. Next question." if section != "Reading Practice" else "Reading accepted. Next sentence.",
            st.session_state.get("interviewer_voice", {}).get("name"),
        )
        move_to_next_n400_question(section)
        st.rerun()

    if st.session_state.n400_flow_attempts < MAX_SPOKEN_ATTEMPTS:
        if st.session_state.get("n400_interview_mode", True):
            st.warning("Not accepted yet. Try again.")
        elif validation.get("close"):
            st.warning(f"Close. Best match: {validation.get('best_answer', '')} | score: {validation.get('score', 0)}")
        else:
            st.warning("Not accepted yet. Try again.")

        speak_feedback_then_pause(
            "Not quite. Try again.",
            st.session_state.get("interviewer_voice", {}).get("name"),
        )
        st.session_state.n400_flow_voice_key = fresh_answer_key()
        st.rerun()

    st.session_state.n400_flow_revealed = True
    st.session_state.n400_flow_voice_key = fresh_answer_key()
    st.rerun()


def n400_flow_report(section):
    results = st.session_state.get("n400_flow_results", [])
    total = len(results)
    spoken_correct = sum(1 for r in results if r.get("final_result") == "spoken_correct")
    knowledge_correct = sum(1 for r in results if r.get("final_result") in ["spoken_correct", "knowledge_correct"])
    missed = sum(1 for r in results if r.get("final_result") == "missed")

    st.header("N-400 Practice Complete")
    st.metric("Spoken accepted", f"{spoken_correct}/{total}")
    st.metric("Knowledge accepted", f"{knowledge_correct}/{total}")
    st.metric("Needs review", missed + (knowledge_correct - spoken_correct))

    st.subheader("Review")
    for i, result in enumerate(results, start=1):
        icon = "✅" if result["final_result"] == "spoken_correct" else "🟡" if result["final_result"] == "knowledge_correct" else "❌"
        st.write(f"{icon} **{i}. {result['question']}**")
        if result.get("transcript"):
            st.caption(f"Transcript: {result['transcript']}")
        if result["final_result"] != "spoken_correct":
            st.caption("Accepted answer(s): " + "; ".join(result.get("answers", [])))
        st.divider()

    if st.button("Practice This N-400 Section Again"):
        start_n400_flow(section)
        st.rerun()


def n400_voice_flow(section):
    bank = get_n400_bank(section)

    if not bank:
        st.warning("No questions loaded for this N-400 section yet.")
        return

    if st.session_state.get("n400_flow_section") != section:
        start_n400_flow(section)

    if st.session_state.get("n400_flow_finished", False):
        n400_flow_report(section)
        return

    raw_item = bank[st.session_state.n400_flow_index]
    item = prepare_n400_item(raw_item, section)
    active_voice = st.session_state.get("interviewer_voice", INTERVIEWER_VOICES[0])

    st.subheader(f"{section}: Question {st.session_state.n400_flow_index + 1} of {len(bank)}")
    st.caption(item["topic"])

    if not st.session_state.get("n400_interview_mode", True) and item.get("study_note"):
        st.info(item["study_note"])

    if section == "Reading Practice":
        st.markdown(f"## {item['question']}")
    else:
        st.markdown(f"### Officer: {item['question']}")

    if not st.session_state.get("n400_flow_started", False):
        if st.button("Begin N-400 Practice"):
            st.session_state.n400_flow_started = True
            speak_text_mac(item["question"], active_voice["name"])
            st.session_state.n400_flow_spoken_index = st.session_state.n400_flow_index
            st.rerun()
        return

    if st.session_state.get("n400_flow_spoken_index") != st.session_state.n400_flow_index:
        speak_text_mac(item["question"], active_voice["name"])
        st.session_state.n400_flow_spoken_index = st.session_state.n400_flow_index

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Repeat Question" if section != "Reading Practice" else "Hear Sentence Again"):
            speak_text_mac(item["question"], active_voice["name"])
    with col2:
        if st.button("Show Answer"):
            st.session_state.n400_flow_revealed = True
            st.session_state.n400_flow_show_answer = True
            st.rerun()
    with col3:
        if st.button("Skip / Next"):
            record_n400_result(item, "skipped", "")
            move_to_next_n400_question(section)
            st.rerun()

    if not st.session_state.get("n400_flow_revealed", False):
        st.markdown("### Please answer now" if section != "Reading Practice" else "### Please read now")
        recorded_answer = st.audio_input("Record answer", key=st.session_state.n400_flow_voice_key)
        process_n400_recording(recorded_answer, item, section)

        if not st.session_state.get("n400_interview_mode", True):
            st.text_area(
                "Transcript captured from voice:",
                value=st.session_state.get("n400_flow_transcript", ""),
                disabled=True,
                height=90,
            )

    if st.session_state.get("n400_flow_revealed", False):
        st.markdown("### Expected answer")
        for answer in item.get("answers", []):
            st.write(f"- {answer}")

        if st.session_state.get("n400_flow_show_answer", False):
            st.caption("Answer revealed by request. You can retry the voice answer or move on with the knowledge check.")
            col_retry, col_next = st.columns(2)
            with col_retry:
                if st.button("Try Voice Again"):
                    st.session_state.n400_flow_revealed = False
                    st.session_state.n400_flow_show_answer = False
                    st.session_state.n400_flow_voice_key = fresh_answer_key()
                    st.rerun()
            with col_next:
                if st.button("Mark Review / Next"):
                    record_n400_result(item, "missed", "show_answer")
                    move_to_next_n400_question(section)
                    st.rerun()

        st.markdown("### Knowledge Check")
        st.caption("Choose the correct answer so we can separate knowledge from pronunciation/transcription.")

        choices = make_n400_choice_options(item.get("answers", []))
        selected = st.radio("Choose the best answer:", choices, index=None, key=st.session_state.n400_flow_choice_key)

        if st.button("Submit Knowledge Check"):
            if not selected:
                st.warning("Choose an answer first.")
            elif is_correct_choice(selected, item.get("answers", [])):
                record_n400_result(item, "knowledge_correct", selected)
                speak_feedback_then_pause(
                    "Correct. Next question.",
                    st.session_state.get("interviewer_voice", {}).get("name"),
                )
                move_to_next_n400_question(section)
                st.rerun()
            else:
                record_n400_result(item, "missed", selected)
                st.error("Still not quite. Moving to the next question.")
                speak_feedback_then_pause(
                    "Not quite. Next question.",
                    st.session_state.get("interviewer_voice", {}).get("name"),
                )
                move_to_next_n400_question(section)
                st.rerun()


def n400_self_test():
    st.subheader("N-400 Self-Test 1")
    st.caption("This is reading comprehension. It auto-scores after the radio-button answer. No typing required.")

    if "n400_self_index" not in st.session_state:
        st.session_state.n400_self_index = 0
        st.session_state.n400_self_score = 0
        st.session_state.n400_self_answered = 0
        st.session_state.n400_self_last_result = ""

    q = N400_SELF_TEST_1[st.session_state.n400_self_index]

    st.caption(f"Question {st.session_state.n400_self_index + 1} of {len(N400_SELF_TEST_1)}")
    if st.session_state.get("n400_self_last_result"):
        st.info(st.session_state.n400_self_last_result)

    st.info(q["passage"])
    st.markdown(f"### {q['question']}")

    answer_key = f"n400_self_radio_{st.session_state.n400_self_index}_{st.session_state.n400_self_answered}"
    selected = st.radio("Choose the best answer:", q["options"], index=None, key=answer_key)

    if selected is not None:
        st.session_state.n400_self_answered += 1
        if selected == q["answer"]:
            st.session_state.n400_self_score += 1
            st.session_state.n400_self_last_result = f"Correct: {selected}"
        else:
            st.session_state.n400_self_last_result = f"Incorrect. You chose {selected}. Correct answer: {q['answer']}"
        st.session_state.n400_self_index = (st.session_state.n400_self_index + 1) % len(N400_SELF_TEST_1)
        time.sleep(0.6)
        st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Score", f"{st.session_state.n400_self_score}/{st.session_state.n400_self_answered}")
    with col2:
        if st.button("Reset Self-Test"):
            for key in list(st.session_state.keys()):
                if key.startswith("n400_self") or key.startswith("n400_scored_"):
                    st.session_state.pop(key, None)
            st.rerun()


def run_n400_module():
    st.title("🇺🇸 N-400 Interview")
    st.caption("Voice-first N-400 practice. No typing unless we later add a separate writing-test module.")

    with st.sidebar:
        st.header("N-400 Controls")
        section = st.radio(
            "N-400 Section",
            ["Personal Interview", "Vocabulary Interview", "Reading Practice", "Self-Test 1"],
            key="n400_section",
        )

        if "n400_interview_mode" not in st.session_state:
            st.session_state.n400_interview_mode = True

        st.session_state.n400_interview_mode = st.toggle(
            "N-400 Interview Mode",
            value=st.session_state.get("n400_interview_mode", True),
            help="Officer asks by voice, expected answers stay hidden, and correct recorded answers auto-advance."
        )

        if st.button("Restart N-400 Section"):
            if section == "Self-Test 1":
                for key in list(st.session_state.keys()):
                    if key.startswith("n400_self"):
                        st.session_state.pop(key, None)
            else:
                start_n400_flow(section)
            st.rerun()

    if section == "Self-Test 1":
        n400_self_test()
    else:
        n400_voice_flow(section)

# -----------------------------
# Streamlit UI
# -----------------------------

st.set_page_config(page_title=APP_TITLE, page_icon="🇺🇸", layout="centered")

st.title("🇺🇸 Ket's Citizenship Trainer")
st.caption("Voice-first interview trainer prototype. Civics and N-400 both use audio-first practice.")

dynamic_data = load_dynamic_answers()

# Sidebar source selector intentionally appears at the very top.
# It must run before civics questions are loaded.
with st.sidebar:
    st.header("Question Source")

    st.session_state.civics_difficulty = st.radio(
        "Civics Exam Difficulty",
        ["Easy", "Hard"],
        horizontal=True,
        index=0 if st.session_state.get("civics_difficulty", "Easy") == "Easy" else 1,
        help="Easy uses questions.json. Hard uses questions_hard.json with reworded questions."
    )

    # QA Sandbox Mode removed from the visible sidebar for beta/stable flow.
    # Leave this off unless manually enabled in code.
    st.session_state.use_qa_questions = False

    st.divider()
    st.header("Practice Area")
    practice_area = st.radio(
        "Choose Practice Area",
        ["Civics Exam", "N-400 Interview"],
        key="practice_area",
    )

if practice_area == "N-400 Interview":
    run_n400_module()
    st.stop()

questions = apply_question_overrides(load_questions(), dynamic_data)
progress = load_progress()

with st.sidebar:
    st.header("Controls")

    st.session_state.interview_mode = st.toggle(
        "Interview Mode",
        value=st.session_state.get("interview_mode", False),
        help="Cleaner USCIS-style screen with fewer study hints."
    )

    mode = "Random Practice"
    special_only = False

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

    st.info("Real USCIS Question Bank Active")
    st.caption("Using: questions.json or questions_hard.json")

    if st.session_state.get("interview_mode", False):
        st.success("Interview Mode Active")
    else:
        st.info("Study Mode Active")
    if dynamic_data.get("dynamic_answers"):
        st.caption(f"Dynamic answers loaded: {dynamic_data.get('state', 'Unknown state')} / {dynamic_data.get('district', 'Unknown district')}")
    else:
        st.warning("No dynamic_answers.json found. Current-officeholder questions may use placeholders.")

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

    if not st.session_state.get("session_saved", False) and results:
        save_completed_session(results)
        st.session_state.session_saved = True

    progress = load_progress()
    all_sessions = progress.get("sessions", [])

    spoken_correct_count = sum(1 for r in results if r["spoken_correct"])
    knowledge_correct_count = sum(1 for r in results if r["knowledge_correct"])
    missed_count = sum(1 for r in results if not r["knowledge_correct"])
    review_count = sum(1 for r in results if r["review_type"] != "none")

    total_count = len(results)

    spoken_score = round((spoken_correct_count / total_count) * 100, 1) if total_count else 0
    knowledge_score = round((knowledge_correct_count / total_count) * 100, 1) if total_count else 0

    st.header("Test Complete")

    st.subheader("Current Test")
    st.metric("Spoken Score", f"{spoken_correct_count}/{total_count} — {spoken_score}%")
    st.metric("Knowledge Score", f"{knowledge_correct_count}/{total_count} — {knowledge_score}%")
    st.metric("Needs Review", review_count)
    st.metric("Missed", missed_count)

    cumulative_total = sum(s.get("total_questions", 0) for s in all_sessions)
    cumulative_spoken = sum(s.get("spoken_correct", 0) for s in all_sessions)
    cumulative_knowledge = sum(s.get("knowledge_correct", 0) for s in all_sessions)
    cumulative_review = sum(s.get("review_needed", 0) for s in all_sessions)
    cumulative_missed = sum(s.get("missed", 0) for s in all_sessions)

    cumulative_spoken_score = round((cumulative_spoken / cumulative_total) * 100, 1) if cumulative_total else 0
    cumulative_knowledge_score = round((cumulative_knowledge / cumulative_total) * 100, 1) if cumulative_total else 0

    st.subheader("Cumulative Practice")
    st.caption("This includes all completed tests saved in progress.json.")
    st.metric("Total questions answered", cumulative_total)
    st.metric("Cumulative spoken score", f"{cumulative_spoken}/{cumulative_total} — {cumulative_spoken_score}%")
    st.metric("Cumulative knowledge score", f"{cumulative_knowledge}/{cumulative_total} — {cumulative_knowledge_score}%")
    st.metric("Cumulative review flags", cumulative_review)
    st.metric("Cumulative missed", cumulative_missed)

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
                extra = ""
                if attempt.get("required_count", 1) > 1:
                    extra = (
                        f" | matched {attempt.get('matched_count', 0)}/"
                        f"{attempt.get('required_count', 1)}"
                    )
                    if attempt.get("matched_answers"):
                        extra += f" ({', '.join(attempt.get('matched_answers', []))})"

                st.caption(
                    f"Attempt {attempt['attempt_number']}: "
                    f"'{attempt['transcript']}' | "
                    f"best match: {attempt['best_answer']} | "
                    f"score: {attempt['score']}"
                    f"{extra}"
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
if not st.session_state.get("interview_mode", False):
    st.write(f"**Category:** {question['category']}")

active_voice = st.session_state.get("interviewer_voice", INTERVIEWER_VOICES[0])

if not st.session_state.get("interview_mode", False):
    st.caption(f"Active interviewer voice: {active_voice['label']}")

st.markdown(f"### {question['question']}")

if question.get("required_count", 1) > 1 and not st.session_state.get("interview_mode", False):
    st.info(f"This question needs {question['required_count']} answers.")

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


if st.session_state.get("interview_mode", False):
    st.markdown("### Please answer now")
else:
    st.markdown("### Spoken Answer")
    st.caption("Record the answer. The app will use the voice transcript as the official submitted answer.")

if sr is None:
    st.error("SpeechRecognition package is not installed. Run: python3 -m pip install SpeechRecognition")


if not st.session_state.revealed:
    recorded_answer = st.audio_input("Record answer", key=st.session_state.answer_widget_key)

    if recorded_answer is not None and not st.session_state.submitted:
        audio_bytes = recorded_answer.getvalue()
        audio_size = len(audio_bytes) if audio_bytes else 0

        # Streamlit can rerun when the user STARTS recording.
        # Do not process until the widget has produced a real audio file.
        if audio_size < MIN_AUDIO_BYTES_TO_PROCESS:
            st.info("Recording... stop the recorder when finished.")
        else:
            with st.spinner("Transcribing and checking answer..."):
                transcript, error = transcribe_audio(recorded_answer)

            if error or not transcript.strip():
                st.warning("I did not catch that clearly. Please try recording again.")
                speak_feedback_then_pause(
                    "I did not catch that. Please try again.",
                    st.session_state.get("interviewer_voice", {}).get("name")
                )

                st.session_state.transcript = ""
                reset_question_state_for_retry()
                st.rerun()

            else:
                st.session_state.transcript = transcript
                st.success(f"Transcript captured: {transcript}")
                process_spoken_submission(question)

    if not st.session_state.get("interview_mode", False):
        st.text_area(
            "Transcript captured from voice:",
            value=st.session_state.get("transcript", ""),
            disabled=True,
            height=90,
        )


# -----------------------------
# Multiple choice remediation
# -----------------------------

if st.session_state.revealed:
    st.markdown("### Knowledge Check")
    if st.session_state.get("interview_mode", False):
        st.caption("Choose the best answer.")
    else:
        st.caption("Spoken answer was not accepted. Choose the best answer so we can separate knowledge from pronunciation/transcription.")

    if st.session_state.get("current_choices") is None:
        st.session_state.current_choices = make_choices(question, questions)

    required_count = int(question.get("required_count", 1) or 1)

    if required_count > 1:
        combo_choices = make_multi_answer_choice_combos(question)

        selected_choice = st.radio(
            f"Choose the best set of {required_count} answer(s):",
            combo_choices,
            index=None,
            key=st.session_state.choice_widget_key,
        )
    else:
        selected_choice = st.radio(
            "Choose the best answer:",
            st.session_state.current_choices,
            index=None,
            key=st.session_state.choice_widget_key,
        )

    if st.button("Submit Multiple Choice"):
        if required_count > 1:
            mc_correct = selected_choice is not None and is_correct_multi_combo(selected_choice, question)
            mc_answer_for_log = selected_choice or ""
        else:
            mc_correct = selected_choice is not None and is_correct_choice(selected_choice, question["answers"])
            mc_answer_for_log = selected_choice or ""

        if not mc_answer_for_log:
            st.warning("Choose an answer first.")

        elif mc_correct:
            progress = load_progress()
            update_question(progress, question["id"], "knowledge_correct")

            st.session_state.session_results.append(
                build_result_record(
                    question=question,
                    final_result="knowledge_correct",
                    mc_answer=mc_answer_for_log,
                )
            )

            st.success("Correct. Knowledge is there. Flagged for pronunciation/transcription review.")

            if st.session_state.current_index + 1 >= len(st.session_state.session_questions):
                speak_feedback_then_pause(
                    "Excellent work. You have completed the USCIS practice exam.",
                    st.session_state.get("interviewer_voice", {}).get("name")
                )
            else:
                speak_feedback_then_pause(
                    "Correct. Next question.",
                    st.session_state.get("interviewer_voice", {}).get("name")
                )

            move_to_next_question()
            st.rerun()

        else:
            progress = load_progress()
            update_question(progress, question["id"], "missed")

            st.session_state.session_results.append(
                build_result_record(
                    question=question,
                    final_result="missed",
                    mc_answer=mc_answer_for_log,
                )
            )

            st.error("Still not quite. Moving to the next question.")

            if st.session_state.current_index + 1 >= len(st.session_state.session_questions):
                speak_feedback_then_pause(
                    "You have completed the USCIS practice exam.",
                    st.session_state.get("interviewer_voice", {}).get("name")
                )
            else:
                speak_feedback_then_pause(
                    "Not quite. Next question.",
                    st.session_state.get("interviewer_voice", {}).get("name")
                )

            move_to_next_question()
            st.rerun()
