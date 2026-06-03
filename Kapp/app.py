import json
import random
import re
from difflib import SequenceMatcher
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

APP_TITLE = "USCIS Citizenship Practice App"
DATA_DIR = Path(__file__).parent / "data"

st.set_page_config(page_title=APP_TITLE, page_icon="🇺🇸", layout="wide")


def load_json(filename: str) -> dict:
    path = DATA_DIR / filename
    if not path.exists():
        st.error(f"Missing data file: {path}")
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize(text: str) -> str:
    text = (text or "").lower().strip()
    text = text.replace("u.s.", "us")
    text = text.replace("d.c.", "dc")
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def fuzzy_score(expected: str, entered: str) -> float:
    return SequenceMatcher(None, normalize(expected), normalize(entered)).ratio()


def speak_button(text: str, label: str = "▶ Play officer voice"):
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


def check_answer(expected: str, user_answer: str, strict: bool = False):
    score = fuzzy_score(expected, user_answer)
    exact = normalize(expected) == normalize(user_answer)
    threshold = 0.96 if strict else 0.84
    if exact:
        return "Correct", score
    if score >= threshold:
        return "Probably OK - meaning looks clear, but practice spelling", score
    return "Needs practice", score


reading = load_json("reading_vocab_m715.json")
writing = load_json("writing_practice.json")
n400_vocab = load_json("n400_vocab_self_test2.json")
n400_personal = load_json("n400_personal_prompts.json")
civics = load_json("civics_sample.json")

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

if module == "Home / Coverage":
    st.subheader("Next Build Coverage")
    st.write("This build adds the missing USCIS resource modules and keeps all practice data generic.")

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
        - **Civics Practice**: starter civics question set, designed so a full JSON can be added later.
        - **N-400 Interview Practice**: generic prompts only, no saved personal data.
        - **N-400 Vocabulary**: Self-Test 2 multiple choice, matching, and fill-in conversation.
        - **Reading Test Practice**: M-715 flashcards, reading sentences, and test simulation.
        - **Writing Test Practice**: officer voice dictation, typed answer check, and forgiving spelling review.
        """
    )

    st.markdown("### No personal information check")
    st.success("Data files contain only generic practice content and placeholders like [your full name].")

elif module == "Civics Practice":
    st.subheader("Civics Practice")
    st.info("This is a starter civics set. Replace data/civics_sample.json with your full civics file when ready.")

    questions = civics.get("questions", [])
    if "civics_idx" not in st.session_state:
        st.session_state.civics_idx = 0
    if st.button("Random civics question"):
        st.session_state.civics_idx = random.randrange(len(questions))

    if questions:
        item = questions[st.session_state.civics_idx % len(questions)]
        speak_button(item["question"])
        big_card("Officer asks", item["question"])
        answer = st.text_input("Type or say the answer, then type it here for checking:", key="civics_answer")
        expected_answers = item.get("answers", [])
        if st.button("Check civics answer"):
            if any(normalize(a) in normalize(answer) or normalize(answer) in normalize(a) for a in expected_answers):
                st.success("Correct / acceptable.")
            else:
                st.warning("Needs practice. Review acceptable answer below.")
            st.write("Acceptable answer(s):", ", ".join(expected_answers))

elif module == "N-400 Interview Practice":
    st.subheader("N-400 Interview Practice")
    st.warning("Do not upload real personal answers to GitHub. This app does not save typed answers to files.")

    prompts = n400_personal.get("prompts", [])
    topic_filter = st.selectbox("Topic", ["All"] + sorted(set(p["topic"] for p in prompts)))
    filtered = prompts if topic_filter == "All" else [p for p in prompts if p["topic"] == topic_filter]

    if "n400_idx" not in st.session_state:
        st.session_state.n400_idx = 0
    if st.button("Random N-400 question"):
        st.session_state.n400_idx = random.randrange(len(filtered))

    if filtered:
        p = filtered[st.session_state.n400_idx % len(filtered)]
        speak_button(p["question"])
        big_card(p["topic"], p["question"])
        st.text_area("Practice answer here. This is not saved:", height=100, key="n400_practice_text")
        with st.expander("Show simple answer pattern"):
            st.write(p["sample_answer"])

elif module == "N-400 Vocabulary":
    st.subheader("N-400 Vocabulary for the Naturalization Interview")
    mode = st.tabs(["Meaning Quiz", "Matching", "Fill in Conversation", "Word List"])

    with mode[0]:
        st.markdown("### Self-Test 2: Choose similar meaning")
        questions = n400_vocab.get("multiple_choice", [])
        if "vocab_mc_idx" not in st.session_state:
            st.session_state.vocab_mc_idx = 0
        if st.button("Random vocabulary question", key="mc_random"):
            st.session_state.vocab_mc_idx = random.randrange(len(questions))
        q = questions[st.session_state.vocab_mc_idx % len(questions)]
        speak_button(q["question"])
        big_card("Question", q["question"])
        choice = st.radio("Choose the best meaning", q["choices"], key=f"mc_{st.session_state.vocab_mc_idx}")
        if st.button("Check answer", key="check_mc"):
            if choice == q["answer"]:
                st.success("Correct.")
            else:
                st.warning("Needs practice.")
            st.write("Answer:", q["answer"])

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
            for term, response in responses.items():
                if response == answers.get(term):
                    correct += 1
                else:
                    st.write(f"**{term}** → {answers.get(term)}")
            st.success(f"Score: {correct} / {len(terms)}")

    with mode[2]:
        st.markdown("### Student Handout A: Fill in the Conversation")
        items = n400_vocab.get("fill_in_conversation", [])
        for i, item in enumerate(items, 1):
            st.write(f"{i}. {item['sentence']}")
            st.text_input("Your answer", key=f"fill_{i}")
        if st.button("Show fill-in answers"):
            for i, item in enumerate(items, 1):
                st.write(f"{i}. **{item['answer']}**")

    with mode[3]:
        st.markdown("### Key words and meanings")
        for item in n400_vocab.get("key_words", []):
            st.write(f"**{item['word']}** = {item['meaning']}")
            st.caption(item["example"])

elif module == "Reading Test Practice":
    st.subheader("M-715 Reading Test Practice")
    tabs = st.tabs(["Flashcards", "Sentence Reading", "Test Simulation", "Coverage"])

    with tabs[0]:
        st.markdown("### Word Flashcards")
        categories = reading.get("categories", {})
        cat = st.selectbox("Category", list(categories.keys()))
        words = categories.get(cat, [])
        word = st.selectbox("Word", words)
        speak_button(word, "▶ Hear word")
        big_card(cat, word)
        st.caption("Student reads this word aloud.")

    with tabs[1]:
        st.markdown("### Reading sentences")
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
        if st.button("Random writing sentence"):
            st.session_state.writing_idx = random.randrange(len(sentences))
        target = sentences[st.session_state.writing_idx % len(sentences)]
        speak_button(target, "▶ Officer says sentence")
        st.caption("Listen first. Type the sentence below. Use Show sentence only after trying.")
        typed = st.text_input("Type the sentence here:", key="writing_typed")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Check writing"):
                result, score = check_answer(target, typed, strict=strict)
                if result == "Correct":
                    st.success(f"{result}. Score: {score:.0%}")
                elif result.startswith("Probably"):
                    st.info(f"{result}. Score: {score:.0%}")
                else:
                    st.warning(f"{result}. Score: {score:.0%}")
                st.write("Expected:", target)
                st.write("Typed:", typed)
        with col_b:
            with st.expander("Show sentence"):
                st.write(target)

    with tabs[1]:
        st.markdown("### Writing vocabulary coverage")
        for cat, words in categories.items():
            with st.expander(f"{cat} — {len(words)} words"):
                st.write(", ".join(words))

st.divider()
st.caption("Build note: This app uses local JSON files only. It does not require API keys and does not store personal answers.")
