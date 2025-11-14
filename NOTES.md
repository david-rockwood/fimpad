# Project Notes

## Streaming mark handling
- Relied on Tk mark gravity when flushing streamed output to avoid overshooting the placeholder when the model emits CRLF or other normalized line endings.
- Added a unit test that simulates CRLF streaming output to ensure the streaming mark remains before the closing `[[[/assistant]]]` tag.
- Verified the behavior with `pytest`.
