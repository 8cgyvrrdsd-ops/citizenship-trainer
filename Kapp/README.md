# USCIS Citizenship Practice App

Local/Streamlit app for citizenship practice using generic USCIS-style materials only.

## What's included

- Civics Practice
  - Officer voice auto-plays on each new question
  - Replay officer voice button
  - Record answer button
  - Transcript returns directly to the app
  - Automatic answer verification after recording
  - Multiple-choice fallback after a wrong answer
  - 20-question scored practice session
  - Blank answers no longer pass

- N-400 Interview Practice
  - Generic prompts only
  - Recommended as speak-aloud practice
  - No personal answer verification
  - No personal answers are saved

- N-400 Vocabulary
  - Meaning quiz with auto-next on correct answers
  - Matching exercise with wrong answers listed under the score
  - Fill-in conversation with green/red feedback under each item
  - Word list for later improvement

- Reading Test Practice
  - M-715 flashcards
  - Sentence reading
  - Test simulation
  - Coverage list

- Writing Test Practice
  - Dictation with officer voice
  - Forgiving answer check
  - Auto-next when correct
  - Feedback plus next-question button when not correct

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Privacy / PI note

This build contains no user personal information. The data files contain only generic USCIS-style practice content and placeholders such as `[your full name]`.

For privacy, the N-400 Interview Practice section should be used mainly for speak-aloud practice. Do not type real personal answers into a public/shared app.

## Microphone note

The record button uses `streamlit-mic-recorder`, which relies on browser speech recognition. Chrome is usually the most reliable browser. This build removes typed civics answers so practice matches the interview flow better.
