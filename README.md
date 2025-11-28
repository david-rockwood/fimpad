# FIMpad

An LLM interface in the form of a tabbed GUI text editor.

FIMpad is currently only tested on Linux, using llama.cpp's llama-server to serve LLMs.

If you have success or run into problems with an OS other than Linux, let me know. I would like to make FIMpad cross platform in the future and have tried to write the code in a way that makes this possible.

---

## Quick start

```bash
git clone https://github.com/david-rockwood/fimpad
cd fimpad
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m fimpad
```

## Overview

FIMpad is an AI sandbox and a text editor. The text editor is the interface to the LLM. AI text generation happens in regular text files, and sessions can be saved to and resumed from a text file. You can do completion or Fill-In-the-Middle (FIM) generation at any point in a text file. And if you are willing to type the control tokens, or use a prepared template with these tokens already typed, you can have standard system/user/assistant chats with an instruct-tuned LLM.

---

## The server

FIMpad requires a connection to an LLM server that provides an OpenAI compatible endpoint. By default FIMpad looks for this endpoint at the base path of `http://localhost:8080`. This base path can be changed in the FIMpad settings window.

Currently FIMpad is likely to only work with llama.cpp's llama-server serving the LLM. In the future, compatibility layers may be added to work with other servers, if there is demand for that.

A recent build of llama.cpp’s llama-server is recommended, available at:
```
https://github.com/ggml-org/llama.cpp
```
When you start llama-server, set a higher context size than the default 4096. Try 16000 or higher to start. Smaller runs faster; larger allows for longer documents and chats. Larger requires more RAM with CPU inference, or more VRAM with GPU inference. The max context size for IBM Granite 4.0 H is 131072.

---

## The LLMs

The recommended model is IBM Granite 4.0 H Base. Granite seems to be the best smaller-sized generalist model that can do FIM currently. Some other models do support FIM, and the FIMpad settings window allows you to set the FIM tokens sent to the server, so some people may be able to get other models working by adjusting those.

Models without FIM tokens will work fine with FIMpad in completion mode, in other words, if there is no suffix. But with a suffix, FIM tokens are sent to the LLM, and if the LLM does not recognize the FIM tokens, it interprets them as plain text, which confuses the response from the LLM. FIMpad provides a way to to disable FIM, but FIMpad is best with a model that has FIM control tokens in the tokenizer.

By default, FIMpad is set up to use the FIM tokens for IBM Granite 4.0 H. To get other models with different FIM tokens to work with FIMpad you have to go into the FIMpad settings window and change the FIM tokens that it sends to the LLM server. For any model you want to try, go to the HuggingFace "Files and versions" page for that model, look in the tokenizer.json file, search for "fim", and if you find FIM tokens for prefix, suffix, and middle, set those in the FIMpad settings window.

But it's easier to just use Granite 4.0 H LLMs if you are new to FIMpad. Many prefer certain LLMs due to the personality/alignment of the assistant, but when you are doing FIM with a base model, alignment is less noticeable.

Granite 4.0 H Small is 32B parameters. Granite 4.0 H Tiny is 7B parameters. Both are MoE models and run faster than dense models of the same size. MoE models don’t activate all parameters at every step. This makes them generally faster with not much of a reduction in capability. With these two models, even without a GPU, you have a fast model in Granite Tiny and a less fast but smarter model in Granite Small.

Granite Small Base is available at:
```
https://huggingface.co/ibm-granite/granite-4.0-h-small-base-GGUF/tree/main
```
Granite Tiny Base is available at:
```
https://huggingface.co/ibm-granite/granite-4.0-h-tiny-base-GGUF/tree/main
```

Granite Small Instruct is available at:
```
https://huggingface.co/ibm-granite/granite-4.0-h-small-GGUF/tree/main

Granite Tiny Instruct is available at:
```
https://huggingface.co/ibm-granite/granite-4.0-h-tiny-GGUF/tree/main
```

Base models are better than instruct models for FIM, though both can work. For system/user/assistant chat, you need an instruct model.

---

## The Library menu

The rightmost menu in FIMpad is the Library menu. The Library menu contains documentation, AI session templates, public domain books, and all of the examples that you will find in this README. When you select something in the Library menu, it opens as a new tab in FIMpad. The files in the Library menu are all .txt and .md files that are bundled with FIMpad.

You will probably find it easier to load the examples below via the Library menu, since copying them from this README.md file can give you leading spaces from the block quote formatting. Find the examples in Library -> README Examples.

## Example 1: A simple completion

FIMpad uses tags enclosed in triple brackets to differentiate FIMpad tags from the rest of the text. There are four classes of tags. We start with the most important type of tag: the FIM tag. 

See how a FIM tag looks before you execute it below.

> Four score and seven[[[50]]]

Here, 50 is the max number of tokens that the LLM will be allowed to generate when the FIM tag is executed. (If you are new to LLMs, estimate two tokens per word, and that will usually be an over-estimation. Often it is closer to one token per word.)

Execute the FIM tag by placing the caret within the FIM tag, or immediately at the end of the tag after the last closing bracket.
The caret is the blinking marker for the position within the text that you are typing. (Many also call this a cursor, but in FIMpad the caret term is used to disambiguate between the text cursor and the mouse cursor.)

With the caret within or immediately after the FIM tag, execute it by pressing Alt+[ (Or select `AI -> Generate` in the menu.) The FIM tag will be deleted, and FIMpad will send the text before the tag to the LLM server as prefix text, and then the LLM server will respond with 50 or fewer tokens that the LLM deems most likely to appear after the prefix. The response will be streamed into the text editor starting at the location where the FIM tag was before it was deleted. When the response completes, it will look something like this:

> Four score and seven years ago our fathers brought forth on this continent, a new nation, conceived in Liberty, and dedicated to the proposition that all men are created equal.
> 
> Now we are engaged in a great civil war, testing whether that nation, or any nation so conceived

There is variability in LLM output, so your results may not look like the above exactly.

## Example 2: Fill in the middle.

In the prior example there was no text after the FIM tag, so it was generated as a completion. But if you are using an LLM capable if FIM (Fill In the Middle), and if you have the FIM tokens for it set correctly in the FIMpad settings window, you will get a FIM generation when you execute a FIM tag and there is text after the tag.

By default, FIMpad is has the proper FIM tokens for IBM Granite 4.0 H LLMs, so if you are using Granite you don't have to worry about setting those tokens.

With FIM tags, text that appears before the FIM tag is *prefix*. Text that appears after the tag is *suffix*.

Let's look at an example that generates a BASH script. It uses a technique that you might call "declare what follows." In the prefix, describe what you want to be generated after the tag. Then optionally give a suffix that is something you would expect to see after whatever you want is generated. See below, before the FIM tag is executed.

> #!/bin/bash
>
> # This script takes a path to a video file ($1) and uses FFMPEG,
> # which is in the PATH, to downscale the video to 480p and
> # render it as an MP4 with AAC audio, with compression for
> # both video and audio that targets small file size with not
> # too much loss of quality. The file name of the rendered video
> # will be the base name of the input file with "_compressed"
> # appended before the extension. The final output 
> # resolution dimensions will be divisible by two without
> # remainder.
> [[[400;temp("0.7");top_p("0.95")]]]
> echo "The file has been rendered successfully."
> exit 0

Below is the result of the above, after executing the tag, using Granite Small Base:

> #!/bin/bash
> 
> # This script takes a path to a video file ($1) and uses FFMPEG,
> # which is in the PATH, to downscale the video to 480p and
> # render it as an MP4 with AAC audio, with compression for
> # both video and audio that targets small file size with not
> # too much loss of quality. The file name of the rendered video
> # will be the base name of the input file with "_compressed"
> # appended before the extension. The final output 
> # resolution dimensions will be divisible by two without
> # remainder.
> 
> echo "Starting compression."
> ffmpeg -i "$1" -vf scale=-2:480 -c:v libx264 -crf 23 -preset veryfast -c:a aac -b:a 128k "${1%.*}_compressed.mp4" -hide_banner
> echo "The file has been rendered successfully."
> exit 0

I tested this script on a 1080p video and it worked.











