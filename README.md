# FIMpad

A lightweight text editor that can do LLM FIM (fill-in-the-middle) and chat within a txt file.

This project is at an early stage. FIMpad has only been run on Linux so far. FIMpad has only been used with llama.cpp llama-server endpoints so far. FIMpad only works with IBM Granite 4.0 H models because of the need FIMpad has for FIM (fill-in-the-middle) tokens in the tokenizer, and the lack (so far, as far as I know) of very many instruct models that are set up for FIM.

## Quick start

```bash
git clone https://github.com/david-rockwood/fimpad.git
cd fimpad
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m fimpad

## FIM Tags

To do an FIM generation, make an FIM tag like this:

[[[N]]]

where N is the max number of tokens that you want to be generated and inserted by the LLM. Then click "Generate". Text will be streamed into the document at the location of the FIM tag.
