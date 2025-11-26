from fimpad.stream_utils import find_stream_match


def _simulate_stream(chunks, patterns):
    output = ""

    for piece in chunks:
        candidate = output + piece
        match = find_stream_match(candidate, patterns)
        if match:
            if match.action == "chop":
                output = candidate[: match.match_index]
            else:
                output = candidate[: match.end_index]
            break

        output = candidate

    return output


def _simulate_buffered_stream(chunks, patterns, accumulated=""):
    buffered = ""

    for piece in chunks:
        candidate = f"{accumulated}{buffered}{piece}"
        match = find_stream_match(candidate, patterns)
        if match:
            target_text = (
                candidate[: match.match_index]
                if match.action == "chop"
                else candidate[: match.end_index]
            )

            if match.action == "chop" and len(target_text) < len(accumulated):
                accumulated = target_text

            pending_insert = target_text[len(accumulated) :]
            buffered = pending_insert
            accumulated += buffered
            break

        buffered += piece

    else:
        accumulated += buffered

    return accumulated


def test_stop_waits_for_pattern():
    patterns = [{"text": "User:", "action": "stop"}]
    chunks = ["Hello", " world", "! Continue..."]

    assert _simulate_stream(chunks, patterns) == "Hello world! Continue..."


def test_stop_keeps_pattern_and_respects_order():
    patterns = [
        {"text": "Assistant:", "action": "stop"},
        {"text": "Assistant", "action": "chop"},
    ]
    chunks = ["Thoughts...", "Assistant:", " ready"]

    assert _simulate_stream(chunks, patterns) == "Thoughts...Assistant:"


def test_chop_removes_pattern_only():
    patterns = [{"text": "END", "action": "chop"}]
    chunks = ["Keep this ", "then END", " and discard"]

    assert _simulate_stream(chunks, patterns) == "Keep this then "


def test_pattern_spanning_chunks_for_stop():
    patterns = [{"text": "STOP!!", "action": "stop"}]
    chunks = ["Waiting ST", "OP!! and more"]

    assert _simulate_stream(chunks, patterns) == "Waiting STOP!!"


def test_pattern_spanning_chunks_for_chop():
    patterns = [{"text": "HALT", "action": "chop"}]
    chunks = ["before HA", "LT trailing text"]

    assert _simulate_stream(chunks, patterns) == "before "


def test_stop_does_not_trigger_on_partial_prefixes():
    patterns = [{"text": "FINAL ANSWER", "action": "stop"}]
    chunks = ["FIN", "ALX ", "ANSWERISH"]

    assert _simulate_stream(chunks, patterns) == "FINALX ANSWERISH"


def test_chop_trims_only_pattern_text():
    patterns = [{"text": "<END>", "action": "chop"}]
    chunks = ["Result: one ", "two <END>", " keep rest"]

    assert _simulate_stream(chunks, patterns) == "Result: one two "


def test_stop_keeps_buffered_trailing_newlines():
    patterns = [{"text": "END\n\n", "action": "stop"}]
    chunks = ["Alpha END\n", "\nOmega"]

    assert _simulate_buffered_stream(chunks, patterns) == "Alpha END\n\n"


def test_chop_removes_already_inserted_pattern():
    patterns = [{"text": "HALT", "action": "chop"}]
    chunks = ["T trailing"]

    assert _simulate_buffered_stream(chunks, patterns, accumulated="before HAL") == "before "
