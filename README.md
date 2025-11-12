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



## The Server

An LLM server must be running on your system and provide an OpenAI compatible endpoint. By default this endpoint should be at the base path of `http://localhost:8080`. This base path can be changed in the FIMpad settings window.

I use llama.cpp llama-server to serve the LLM, but it is my understanding that other servers should be able work with FIMpad if they provide an OpenAI compatible endpoint.

The LLM served must be IBM Granite 4.0 H. FIM pad requires FIM tokens be in the model's tokenizer. Granite is the best smaller-sized generalist model that I have found that does this so far. With other LLMs, you should still be able to do Chat in FIMpad, but if you try to do fill-in-the-middle generation with a model other than Granite 4.0 H you will likely run into problems.

I suggest using a recent build of llama.cpp llama-server available at:
```
https://github.com/ggml-org/llama.cpp
```

I suggest the Q6 version of Granite Small available at:
```
https://huggingface.co/ibm-granite/granite-4.0-h-small-GGUF/tree/main
```
and the Q6 version of Granite Tiny available at:
```
https://huggingface.co/ibm-granite/granite-4.0-h-tiny-GGUF
```


## Overview

With FIMpad, you can have AI sessions with a local LLM in a notepad-like text editor. You can do fill-in-the middle generation at any point in a text file. If you do fill-in-the-middle at the very end of a text file, it works like completion. Fill-in-the-middle is a versatile and quick way to help with story writing and coding, among other things.

FIMpad can also chat with the LLM using the standard system, user, and assistant roles. A text document is a good interface for LLM chat because you can edit chat history, and because you can save a text file that works as a save state for the session. You can save prefills the same way. You can resume a session at a later date by simply reopening the text file. You can save notes outside the chat tags.



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

In order to control which text is sent to the LLM as context for FIM generation, you can use the [[[prefix]]] and [[[suffix]]] tags.











