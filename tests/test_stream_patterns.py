from fimpad.stream_utils import compute_stream_tail, find_stream_match


def _simulate_stream(chunks, patterns):
    output = ""
    tail = ""

    for piece in chunks:
        match = find_stream_match(tail, piece, patterns)
        if match:
            if match.append_len:
                output += piece[: match.append_len]
            if match.action == "chop" and match.pattern:
                output = output[: -len(match.pattern)]
            break

        output += piece
        tail = compute_stream_tail(tail, piece, patterns)

    return output


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
