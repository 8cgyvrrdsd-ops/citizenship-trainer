from pathlib import Path
import re

path = Path("app.py")
text = path.read_text()

pattern = re.compile(
    r"""st\.markdown\(\s*["'].*?Record Answer.*?\)\s*\n\s*recorded_answer\s*=\s*st\.audio_input\([\s\S]*?\)\s*""",
    re.DOTALL,
)

replacement = '''st.markdown(
    "<div style='font-size:16px; font-weight:600; color:#cc0000; margin-bottom:-10px;'>Record Answer</div>",
    unsafe_allow_html=True
)

recorded_answer = st.audio_input(
    "Record Answer",
    label_visibility="collapsed",
    key=f"audio_answer_{st.session_state.current_question_index}"
)
'''

new_text, count = pattern.subn(replacement, text, count=1)

if count == 0:
    print("Could not find recorder block. No changes made.")
else:
    path.write_text(new_text)
    print("Fixed recorder block.")
