# FIMpad

A text editor focused on LLM FIM (fill-in-the-middle) workflows within a text file.

The first release will likely be in December 2025.

## Quick start

```bash
git clone https://github.com/david-rockwood/fimpad
cd fimpad
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m fimpad
```

## Overview

FIMpad is an AI sandbox and a text editor. The text editor is the interface to the LLM. AI workflows live in regular text files, and sessions can be saved to and resumed from a text file. You can do fill-in-the-middle generation at any point in a text file. Fill-in-the-middle generation is a versatile, powerful, and quick way to help with story writing and coding, among many other things.

## The server

FIMpad requires a connection to a LLM server that provides an OpenAI compatible endpoint. By default FIMpad looks for this endpoint at the base path of `http://localhost:8080`. This base path can be changed in the FIMpad settings window.

A recent build of llama.cpp llama-server is recommended, available at:
```
https://github.com/ggml-org/llama.cpp
```
When you start llama-server, set a higher context size than the default 4096. Try 16000 to start. Smaller runs faster, larger allows for longer documents and chats. Larger requires more RAM with CPU inference, or more VRAM with GPU inference. The max context size for IBM Granite 4.0 H is 131072.

## The LLMs

The LLM served should be IBM Granite 4.0 H. FIMpad requires that FIM tokens be in the model's tokenizer. Granite seems to be the best smaller-sized generalist model that can do FIM currently. Some other models do support FIM, and the FIMpad settings window allows you to set the FIM tokens sent to the server, so some people may be able to get other models working by adjusting those. In one brief test, CWC-Mistral-Nemo worked for FIM without adjusting any FIMpad settings.

Granite Small is 32B parameters. Granite Tiny is 7B parameters. Both are MoE models and run faster than dense models of the same size. MoE models don’t activate all parameters on every step. This makes them generally faster with not much of a reduction in capability. With these two models, even without a GPU, you have a fast model in Granite Tiny and a less fast but smarter model in Granite Small.

Granite Small is available at:
```
https://huggingface.co/ibm-granite/granite-4.0-h-small-GGUF/tree/main
```
Granite Tiny is available at:
```
https://huggingface.co/ibm-granite/granite-4.0-h-tiny-GGUF/tree/main
```

## Let us begin

Once you have your server running, open FIMpad. All examples of FIM generation below were generated using llama-server and Granite Small at Q6 quantization.

## FIM tags

All tags in FIMpad are enclosed in triple brackets, in order to strongly differentiate tags from regular text. Of the the four classes of tags in FIMpad, FIM tags are the most important. A FIM tag marks the location in a text file where you want the LLM-generated text to be inserted. Below is an example of a simple FIM tag before insertion.

> Four score and seven[[[50]]]


The number 50 is enclosed in triple brackets. This FIM tag will stream a maximum of 50 tokens into the document. The tag will be deleted before streaming insertion. To execute a FIM tag, click inside the FIM tag such that the carat is within or directly adjacent to the FIM tag. Then press Ctrl+Enter (or use the menu entry at AI->Generate.) Below is an example of the result (although your result may not be an exact match due to the variability of LLM generation.).

> Four score and seven years ago, our fathers brought forth on this continent, a new nation, conceived in Liberty, and dedicated to the proposition that all men are created equal. Now we are engaged in a great civil war, testing whether that nation, or any nation so


Upon execution of the FIM tag, the tag is deleted from the document. All of the text between the beginning of the file (BOF) and the location of the now-deleted FIM tag is considered **prefix text**. All of the text between the now-deleted FIM tag and the end of the file (EOF) is considered **suffix text**. The prefix and the suffix are sent to the LLM server, and then the LLM server streams back the 50 tokens that the LLM deems most likely to appear between the prefix and the suffix. In the example above, the document was empty past the FIM tag, so the LLM received an empty string for the suffix. In cases like this the streamed response is essentially a completion of the prefix.













