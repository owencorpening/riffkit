import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("compare_lyrics", ROOT / "scripts" / "compare_lyrics.py")
cl = importlib.util.module_from_spec(spec)
sys.modules["compare_lyrics"] = cl  # dataclasses look the module up here
spec.loader.exec_module(cl)

# Made-up text only: no real lyrics in the repo.
KEY = """\
# made-up key
the blue kettle sings at noon

we walk the long road home
"""


def _transcript(text):
    """A transcript in transcribe_adaptive.py's segments/words shape."""
    words = [{"word": " " + w, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, w in enumerate(text.split())]
    return {"segments": [{"start": 0.0, "end": len(words) * 0.5, "text": " " + text, "words": words}]}


def _score(text, key=KEY):
    lines = [words for _, words in cl.parse_key(key)]
    return cl.score(lines, cl.transcript_words(_transcript(text)))


def test_parse_key_skips_blank_and_comment_lines():
    key = cl.parse_key(KEY)
    assert [line for line, _ in key] == ["the blue kettle sings at noon", "we walk the long road home"]


def test_normalize_lowercases_strips_punctuation_keeps_inner_apostrophes():
    assert cl.normalize("Don't STOP, 'now' -- rock'n'roll!") == ["don't", "stop", "now", "rock'n'roll"]


def test_perfect_match():
    first, second = _score("The blue kettle sings at noon. We walk the long road home!")
    assert (first.correct, first.wrong, first.missing, first.invented) == (6, 0, 0, 0)
    assert (second.correct, second.wrong, second.missing, second.invented) == (6, 0, 0, 0)
    assert first.passed and second.passed


def test_wrong_word():
    first, second = _score("the blue kettle rings at noon we walk the long road home")
    assert (first.correct, first.wrong, first.missing, first.invented) == (5, 1, 0, 0)
    assert not first.passed
    assert second.correct == 6 and second.passed


def test_missing_word():
    first, second = _score("the blue kettle sings at noon we walk the road home")
    assert first.correct == 6
    assert (second.correct, second.wrong, second.missing, second.invented) == (5, 0, 1, 0)


def test_invented_word():
    first, second = _score("the blue kettle sings at noon we walk the long long road home")
    assert first.invented == 0
    assert (second.correct, second.wrong, second.missing, second.invented) == (6, 0, 0, 1)
    # Invented words don't reduce the share of key words that are correct.
    assert second.passed


def test_words_are_attributed_to_their_key_line():
    # Errors only in the second line, transcript runs both lines together.
    first, second = _score("the blue kettle sings at noon we talk the long toad home")
    assert first.correct == 6 and first.passed
    assert second.correct == 4 and second.wrong == 2 and not second.passed


def test_words_inserted_between_lines_count_on_the_earlier_line():
    first, second = _score("the blue kettle sings at noon oh yeah we walk the long road home")
    assert first.invented == 2
    assert second.invented == 0


def test_pass_needs_at_least_ninety_percent():
    key = "one two three four five six seven eight nine ten\n"
    (exactly_90,) = _score("one two three four five six seven eight nine tin", key)
    (below_90,) = _score("one two three four five six seven eight nun tin", key)
    assert exactly_90.correct == 9 and exactly_90.passed
    assert below_90.correct == 8 and not below_90.passed


def test_main_prints_side_by_side_table_and_totals(tmp_path, capsys):
    key = tmp_path / "key.txt"
    key.write_text(KEY, encoding="utf-8")
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_transcript("the blue kettle sings at noon we walk the long road home")))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_transcript("the blue kettle rings at noon we walk the long road home")))

    assert cl.main([str(key), str(good), str(bad)]) == 0
    out = capsys.readouterr().out
    header = out.splitlines()[0]
    assert "good" in header and "bad" in header
    assert cl.GREEN + "PASS 6/6" in out
    assert cl.RED + "FAIL 5/6 w1" in out
    assert "good: 12/12 words correct, word error rate 0.0%, 2/2 lines passed" in out
    assert "bad: 11/12 words correct, word error rate 8.3%, 1/2 lines passed" in out
