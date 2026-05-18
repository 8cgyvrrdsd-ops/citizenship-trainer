import streamlit as st
import random

SELF_TEST_1 = [
    {
        "passage": "The employee’s name is Mr. John David Fenton.",
        "question": "What is his first name?",
        "options": ["Mr.", "John", "David"],
        "answer": "John",
    },
    {
        "passage": "Bill was born in Australia and now lives in Chicago, Illinois.",
        "question": "What is Bill’s country of birth?",
        "options": ["Australia", "Illinois", "United States"],
        "answer": "Australia",
    },
    {
        "passage": "Tom works as a doctor at Mount Carmel Hospital.",
        "question": "What is Tom’s occupation?",
        "options": ["a doctor", "two years", "Mount Carmel Hospital"],
        "answer": "a doctor",
    },
]

VOCAB_WORDS = [
    ("habitually", "often"),
    ("verify", "prove something is true"),
    ("marital status", "married, divorced, single, or widowed"),
    ("swear", "promise"),
    ("registered", "signed up"),
    ("spouse", "husband or wife"),
    ("current home address", "where you live now"),
    ("date of birth", "when you were born"),
    ("federal", "U.S. government"),
    ("resident", "someone who lives in"),
]

READING_VOCAB = [
    "Abraham Lincoln",
    "George Washington",
    "American flag",
    "Congress",
    "President",
    "White House",
    "United States",
    "citizen",
    "vote",
    "Independence Day",
]

INTERVIEW_TOPICS = {
    "Name": [
        "What is your full legal name?",
        "Have you ever used another name?",
    ],
    "Birth": [
        "What is your date of birth?",
        "Where were you born?",
    ],
    "Address": [
        "What is your current address?",
        "Where did you live before this?",
    ],
    "Employment": [
        "Where do you work?",
        "What is your occupation?",
    ],
    "Family": [
        "What is your marital status?",
        "Do you have children?",
    ],
    "Travel": [
        "Have you traveled outside the United States?",
        "How long were you outside the United States?",
    ],
}


def mock_interview():
    st.header("Mock Interview Practice")

    topic = st.selectbox("Choose Topic", list(INTERVIEW_TOPICS.keys()))

    for question in INTERVIEW_TOPICS[topic]:
        st.markdown(f"**Officer:** {question}")
        st.text_input("Practice Your Answer", key=f"n400_{topic}_{question}")


def self_test_quiz():
    st.header("Self-Test Quiz")

    if "n400_quiz_index" not in st.session_state:
        st.session_state.n400_quiz_index = 0
        st.session_state.n400_quiz_score = 0

    q = SELF_TEST_1[st.session_state.n400_quiz_index]

    st.info(q["passage"])

    answer = st.radio(
        q["question"],
        q["options"],
        key=f"n400_quiz_{st.session_state.n400_quiz_index}"
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Submit"):
            if answer == q["answer"]:
                st.success("Correct!")
                st.session_state.n400_quiz_score += 1
            else:
                st.error(f"Incorrect. Correct answer: {q['answer']}")

    with col2:
        if st.button("Next"):
            st.session_state.n400_quiz_index += 1
            if st.session_state.n400_quiz_index >= len(SELF_TEST_1):
                st.session_state.n400_quiz_index = 0
            st.rerun()

    with col3:
        if st.button("Reset"):
            st.session_state.n400_quiz_index = 0
            st.session_state.n400_quiz_score = 0
            st.rerun()

    st.write(f"Score: {st.session_state.n400_quiz_score}")


def vocabulary():
    st.header("N-400 Vocabulary")

    word, meaning = random.choice(VOCAB_WORDS)

    st.subheader(word)
    st.write(f"Meaning: {meaning}")

    st.text_input("Type a sentence using this word", key=f"n400_vocab_{word}")


def reading_practice():
    st.header("Reading Practice")

    st.write("These are USCIS reading-test vocabulary words. The applicant may be asked to read a simple sentence using these words.")

    search = st.text_input("Search Reading Words")

    filtered = [
        word for word in READING_VOCAB
        if search.lower() in word.lower()
    ]

    for word in filtered:
        st.markdown(f"- **{word}**")


def run_n400_module():
    st.title("🇺🇸 N-400 Practice Module")

    section = st.sidebar.selectbox(
        "N-400 Section",
        [
            "Mock Interview",
            "Self-Test Quiz",
            "Vocabulary",
            "Reading Practice",
        ],
        key="n400_sidebar_section"
    )

    if section == "Mock Interview":
        mock_interview()
    elif section == "Self-Test Quiz":
        self_test_quiz()
    elif section == "Vocabulary":
        vocabulary()
    elif section == "Reading Practice":
        reading_practice()
