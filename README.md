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
```



## The Two Tag Classes

There are two classes of tags in FIMpad: FIM tags and Chat tags. The FIM tags enable fill-in-the-model insertion of text from an LLM into the text file. The Chat tags enable chat with an LLM; with system, user, and assistant messages.



## FIM tags

To do an FIM generation, make an FIM tag like this:
```
[[[N]]]
```
where N is the max number of tokens that you want to be generated and inserted into the text file by the LLM. N must be a positive integer greater than zero. Click "Generate" and the FIM tag will be deleted and text from the LLM will be streamed into the text file at the location where the FIM tag was before it was deleted.

For FIM generation, everything in the text file before the FIM tag is sent to the LLM as prefix text, and everything in the text file after the FIM tag is sent to the LLM as suffix text. The LLM uses both prefix text and suffix text as context, and it sends back text that it deems likely to appear between them. However, sometimes you won't want all the text in the text file to be sent as either prefix or suffix text. This is where the [[[prefix]]] and [[[suffix]]] tags come in.

### Prefix and Suffix Tags (only work for FIM generation)











