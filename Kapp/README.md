# USCIS Citizenship Practice App - Next Build

## What this build adds
- M-715 Reading Vocabulary module
- Writing Test Practice module using official-style USCIS writing vocabulary sentences
- N-400 Vocabulary Self-Test 2 module
  - Multiple choice meaning quiz
  - Matching exercise
  - Fill-in conversation exercise
- Generic N-400 Interview Practice prompts
- No personal information in uploaded files

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Files to upload to GitHub
Upload all of these:
- `app.py`
- `requirements.txt`
- `README.md`
- `data/reading_vocab_m715.json`
- `data/writing_practice.json`
- `data/n400_vocab_self_test2.json`
- `data/n400_personal_prompts.json`
- `data/civics_sample.json`

## Privacy note
This build contains no real applicant personal information. Personal answers typed during practice are not saved to files.
