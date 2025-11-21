# FIMpad

A lightweight text editor focused on LLM FIM (fill-in-the-middle) workflows within a text file.

The first release will likely be in December 2025.

## Quick start

```bash
git clone https://github.com/david-rockwood/fimpad
cd fimpad
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m fimpad
```

## The Server

FIMpad requires a connection to a LLM server that provides an OpenAI compatible endpoint. By default FIMpad looks for this endpoint at the base path of `http://localhost:8080`. This base path can be changed in the FIMpad settings window.

I use llama.cpp llama-server to serve the LLM, but it is my understanding that other servers should be able to work with FIMpad if they provide an OpenAI compatible endpoint.

The LLM served should be IBM Granite 4.0 H. FIMpad requires that FIM tokens be in the model's tokenizer. Granite is the best smaller-sized generalist model that I have found that does this so far. However, I did try FIM with a variant of Mistral-Nemo and it worked. But then I tried Mistral Small and FIM did not work. The FIMpad settings window allows you to set the FIM tokens sent to the server, so some people may be able to get other models working by adjusting those. But at the moment I am only focused on supporting IBM Granite 4.0 H.

I suggest using a recent build of llama.cpp llama-server available at:
```
https://github.com/ggml-org/llama.cpp
```

When you start llama-server, set a higher context size than the default 4096. Try 16000 to start. Smaller runs faster, bigger allows for longer documents and chats. Bigger requires more RAM with CPU inference, more VRAM with GPU inference. The max for IBM Granite 4.0 H is 131072.

## The LLMs

I suggest the Q6 version of Granite Small available at:
```
https://huggingface.co/ibm-granite/granite-4.0-h-small-GGUF/tree/main
```
and the Q6 version of Granite Tiny available at:
```
https://huggingface.co/ibm-granite/granite-4.0-h-tiny-GGUF/tree/main
```

Granite Small is 32B parameters. Granite Tiny is 7B parameters. Both are MoE models and run faster than dense models of the same size. MoE models choose a small number of expert subnetworks per token, so they don’t activate all parameters on every step. This makes them generally faster with not much of a reduction in capability. With these two models, even without a GPU, you have a fast model in Granite Tiny and a less fast but smarter model in Granite Small.

## Overview

With FIMpad, you can have AI sessions with a local LLM in a notepad-like text editor. You can do fill-in-the-middle generation at any point in a text file. If you do fill-in-the-middle at the very end of a text file, it works like completion. Fill-in-the-middle is a versatile and quick way to help with story writing and coding, among many other things.
