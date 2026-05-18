#!/usr/bin/env python3
"""
build_hard_mode.py
Run from inside your Kapp folder.
Creates questions_hard.json from questions.json and lightly patches app.py:
- Easy/Hard Civics Exam switch
- /data folder support for JSON files
- label cleanup: Civics Exam / N-400 Interview
"""
import json
import re
from pathlib import Path

BASE = Path(__file__).parent
APP = BASE / "app.py"

def existing_path(*paths):
    for p in paths:
        if p.exists():
            return p
    return paths[0]

QUESTIONS = existing_path(BASE / "questions.json", BASE / "data" / "questions.json")
if not QUESTIONS.exists():
    raise FileNotFoundError("Could not find questions.json in Kapp/ or Kapp/data/")

HARD = QUESTIONS.parent / "questions_hard.json"

SPECIFIC = {
    "what is the supreme law of the land": "Which document is the highest law in the United States?",
    "what does the constitution do": "What are the main things the Constitution does for the United States?",
    "what is an amendment": "What do we call a change or addition to the Constitution?",
    "what do we call the first ten amendments to the constitution": "What name is given to the first ten amendments to the Constitution?",
    "what is one right or freedom from the first amendment": "Name one right or freedom protected by the First Amendment.",
    "how many amendments does the constitution have": "How many total amendments have been added to the Constitution?",
    "what did the declaration of independence do": "What action did the Declaration of Independence take for the American colonies?",
    "what are two rights in the declaration of independence": "Name two rights listed in the Declaration of Independence.",
    "what is freedom of religion": "What does freedom of religion allow people in the United States to do?",
    "what is the economic system in the united states": "What kind of economic system does the United States use?",
    "what is the rule of law": "What does the rule of law mean in the United States?",
    "name one branch or part of the government": "Name one branch or part of the United States government.",
    "what stops one branch of government from becoming too powerful": "What system keeps one branch of government from becoming too powerful?",
    "who is in charge of the executive branch": "Who leads the executive branch of the United States government?",
    "who makes federal laws": "Which part of the government makes federal laws?",
    "what are the two parts of the u.s. congress": "What are the two chambers that make up the United States Congress?",
    "how many u.s. senators are there": "How many United States senators serve in the Senate?",
    "we elect a u.s. senator for how many years": "For how many years is a United States senator elected?",
    "who is one of your state’s u.s. senators now": "Name one current United States senator from your state.",
    "the house of representatives has how many voting members": "How many voting members are in the House of Representatives?",
    "we elect a u.s. representative for how many years": "For how many years is a United States representative elected?",
    "name your u.s. representative": "Who is your current United States representative?",
    "who does a u.s. senator represent": "Who is represented by a United States senator?",
    "why do some states have more representatives than other states": "Why do some states receive more members in the House of Representatives than other states?",
    "we elect a president for how many years": "For how many years is the president elected?",
    "in what month do we vote for president": "During which month is the presidential election held?",
    "what is the name of the president of the united states now": "Who is the current president of the United States?",
    "what is the name of the vice president of the united states now": "Who is the current vice president of the United States?",
    "if the president can no longer serve, who becomes president": "Who becomes president if the president can no longer serve?",
    "if both the president and the vice president can no longer serve, who becomes president": "Who becomes president if neither the president nor the vice president can serve?",
    "who is the commander in chief of the military": "Who serves as commander in chief of the United States military?",
    "who signs bills to become laws": "Who must sign a bill before it becomes law?",
    "who vetoes bills": "Who has the power to veto bills?",
    "what does the president’s cabinet do": "What is the role of the president’s Cabinet?",
    "what are two cabinet-level positions": "Name two Cabinet-level positions in the federal government.",
    "what does the judicial branch do": "What responsibilities belong to the judicial branch?",
    "what is the highest court in the united states": "Which court is the highest court in the United States?",
    "how many justices are on the supreme court": "How many justices serve on the Supreme Court?",
    "who is the chief justice of the united states now": "Who is the current Chief Justice of the United States?",
    "who is the governor of your state now": "Who is the current governor of your state?",
    "what is the capital of your state": "What city is the capital of your state?",
    "what are the two major political parties in the united states": "Name the two major political parties in the United States.",
    "what is the political party of the president now": "What is the current president’s political party?",
    "what is the name of the speaker of the house of representatives now": "Who is the current Speaker of the House of Representatives?",
    "what is one responsibility that is only for united states citizens": "Name one responsibility that only United States citizens have.",
    "name one right only for united states citizens": "Name one right that only United States citizens have.",
    "what are two rights of everyone living in the united states": "Name two rights that everyone living in the United States has.",
    "what do we show loyalty to when we say the pledge of allegiance": "When saying the Pledge of Allegiance, what do we promise loyalty to?",
    "what is one promise you make when you become a united states citizen": "Name one promise made during the Oath of Allegiance when becoming a United States citizen.",
    "how old do citizens have to be to vote for president": "What is the minimum age for citizens to vote for president?",
    "what are two ways that americans can participate in their democracy": "Name two ways Americans can take part in democracy.",
    "when is the last day you can send in federal income tax forms": "What is the deadline for sending federal income tax forms?",
    "when must all men register for the selective service": "At what age must men register for Selective Service?",
    "what is one reason colonists came to america": "Name one reason colonists originally came to America.",
    "who lived in america before the europeans arrived": "Who lived in America before Europeans arrived?",
    "what group of people was taken to america and sold as slaves": "What group of people was brought to America and sold into slavery?",
    "why did the colonists fight the british": "Why did the American colonists fight against the British?",
    "who wrote the declaration of independence": "Who was the main writer of the Declaration of Independence?",
    "when was the declaration of independence adopted": "On what date was the Declaration of Independence adopted?",
    "there were 13 original states. name three": "Name three of the original thirteen states.",
    "what happened at the constitutional convention": "What important work was done at the Constitutional Convention?",
    "when was the constitution written": "In what year was the Constitution written?",
    "what is one thing benjamin franklin is famous for": "Name one thing Benjamin Franklin is known for.",
    "who is the “father of our country”": "Who is known as the Father of Our Country?",
    "who was the first president": "Who was the first president of the United States?",
    "what territory did the united states buy from france in 1803": "What land did the United States purchase from France in 1803?",
    "name one war fought by the united states in the 1800s": "Name one war the United States fought during the 1800s.",
    "name the u.s. war between the north and the south": "What was the name of the war fought between the North and the South in the United States?",
    "name one problem that led to the civil war": "Name one issue that led to the Civil War.",
    "what was one important thing that abraham lincoln did": "Name one important action or achievement of Abraham Lincoln.",
    "what did the emancipation proclamation do": "What did the Emancipation Proclamation accomplish?",
    "what did susan b. anthony do": "What is Susan B. Anthony known for?",
    "name one war fought by the united states in the 1900s": "Name one war the United States fought during the 1900s.",
    "who was president during world war i": "Who was president during World War I?",
    "who was president during the great depression and world war ii": "Who was president during the Great Depression and World War II?",
    "who did the united states fight in world war ii": "Which countries did the United States fight against in World War II?",
    "before he was president, eisenhower was a general. what war was he in": "Before becoming president, Dwight Eisenhower served as a general in which war?",
    "during the cold war, what was the main concern of the united states": "What was the United States mainly concerned about during the Cold War?",
    "what movement tried to end racial discrimination": "What movement worked to end racial discrimination in the United States?",
    "what did martin luther king, jr. do": "What is Martin Luther King Jr. known for doing?",
    "what major event happened on september 11, 2001, in the united states": "What major attack occurred in the United States on September 11, 2001?",
    "name one american indian tribe in the united states": "Name one American Indian tribe in the United States.",
    "name one of the two longest rivers in the united states": "Name one of the two longest rivers in the United States.",
    "what ocean is on the west coast of the united states": "Which ocean is on the West Coast of the United States?",
    "what ocean is on the east coast of the united states": "Which ocean is on the East Coast of the United States?",
    "name one u.s. territory": "Name one territory of the United States.",
    "name one state that borders canada": "Name one state that shares a border with Canada.",
    "name one state that borders mexico": "Name one state that shares a border with Mexico.",
    "what is the capital of the united states": "What city is the capital of the United States?",
    "where is the statue of liberty": "Where is the Statue of Liberty located?",
    "why does the flag have 13 stripes": "Why are there thirteen stripes on the United States flag?",
    "why does the flag have 50 stars": "Why are there fifty stars on the United States flag?",
    "what is the name of the national anthem": "What is the national anthem of the United States called?",
    "when do we celebrate independence day": "On what date do Americans celebrate Independence Day?",
    "name two national u.s. holidays": "Name two national holidays in the United States.",
}

def norm(q):
    q = re.sub(r"\s+", " ", q).strip().lower().rstrip("?")
    q = q.replace("’", "'").replace("“", '"').replace("”", '"')
    return q

def hard_rewrite(question):
    q = re.sub(r"\s+", " ", question).strip()
    low = norm(q)
    if low in SPECIFIC:
        return SPECIFIC[low]
    if low.startswith("what is "):
        return "Explain this civics concept: " + q
    if low.startswith("who is ") or low.startswith("who was "):
        return "Identify the person asked about here: " + q
    if low.startswith("name one "):
        return "Give one correct example: " + q
    if low.startswith("name two "):
        return "Give two correct examples: " + q
    if low.startswith("how many "):
        return "State the correct number: " + q
    if low.startswith("why "):
        return "Explain the reason: " + q
    if low.startswith("when "):
        return "State the correct time or date: " + q
    return "Answer this civics question in your own words: " + q

questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
hard_questions = []
for item in questions:
    new = dict(item)
    new["easy_question"] = item.get("question", "")
    new["question"] = hard_rewrite(item.get("question", ""))
    new["difficulty"] = "hard"
    hard_questions.append(new)

HARD.write_text(json.dumps(hard_questions, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Created {HARD} with {len(hard_questions)} questions")

if not APP.exists():
    print("app.py not found; only questions_hard.json was created.")
    raise SystemExit

text = APP.read_text(encoding="utf-8")
backup = BASE / "app_backup_before_hard_mode.py"
if not backup.exists():
    backup.write_text(text, encoding="utf-8")
    print(f"Backup saved: {backup}")

# patch constants with /data support
repls = {
    'QUESTIONS_FILE = Path("questions.json")': 'QUESTIONS_FILE = existing_path(Path("questions.json"), Path("data/questions.json"))\nQUESTIONS_HARD_FILE = existing_path(Path("questions_hard.json"), Path("data/questions_hard.json"))',
    'QA_QUESTIONS_FILE = Path("questions_multi_answer_QA.json")': 'QA_QUESTIONS_FILE = existing_path(Path("questions_multi_answer_QA.json"), Path("data/questions_multi_answer_QA.json"))',
    'PROGRESS_FILE = Path("progress.json")': 'PROGRESS_FILE = existing_path(Path("progress.json"), Path("data/progress.json"))',
    'DYNAMIC_ANSWERS_FILE = Path("dynamic_answers.json")': 'DYNAMIC_ANSWERS_FILE = existing_path(Path("dynamic_answers.json"), Path("data/dynamic_answers.json"))',
}

helper = '''\ndef existing_path(*paths):\n    for path in paths:\n        if path.exists():\n            return path\n    return paths[0]\n'''
if "def existing_path(" not in text:
    # must be before constants get used
    text = text.replace('APP_TITLE = "Ket\'s Citizenship Trainer"', 'APP_TITLE = "Ket\'s Citizenship Trainer"' + helper)

if "QUESTIONS_HARD_FILE" not in text:
    for old, new in repls.items():
        text = text.replace(old, new)
else:
    # still patch /data support if not already patched
    for old, new in repls.items():
        if old in text:
            text = text.replace(old, new)

old_load = '''    if QUESTIONS_FILE.exists():\n        return json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))'''
new_load = '''    active_file = QUESTIONS_HARD_FILE if st.session_state.get("civics_difficulty", "Easy") == "Hard" else QUESTIONS_FILE\n\n    if active_file.exists():\n        return json.loads(active_file.read_text(encoding="utf-8"))'''
if old_load in text and "active_file = QUESTIONS_HARD_FILE" not in text:
    text = text.replace(old_load, new_load)

diff_block = '''\n    st.session_state.civics_difficulty = st.radio(\n        "Civics Exam Difficulty",\n        ["Easy", "Hard"],\n        horizontal=True,\n        index=0 if st.session_state.get("civics_difficulty", "Easy") == "Easy" else 1,\n        help="Easy uses questions.json. Hard uses questions_hard.json with reworded questions."\n    )\n'''
if "Civics Exam Difficulty" not in text:
    text = text.replace('    st.header("Question Source")\n', '    st.header("Question Source")\n' + diff_block)

text = text.replace("Civics Practice", "Civics Exam")
text = text.replace("N-400 Practice", "N-400 Interview")

APP.write_text(text, encoding="utf-8")
print("Patched app.py. Now run: streamlit run app.py")
