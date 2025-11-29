# FIMpad

FIMpad is a FIM-focused local LLM interface in the form of a tabbed GUI text editor.

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

---

## Overview

FIMpad is an AI sandbox and a text editor. The text editor is the interface to the LLM. AI text generation happens in regular text files, and sessions can be saved to and resumed from a text file. You can do completion or FIM (Fill In the Middle) generation at any point in a text file.

---

## The server

FIMpad requires a connection to an LLM server that provides an OpenAI compatible endpoint. By default FIMpad looks for this endpoint at the base path of `http://localhost:8080`. This base path can be changed in the FIMpad settings window.

Currently, FIMpad is only known to work with llama.cpp's llama-server serving the LLM.

A recent build of llama.cpp’s llama-server is recommended, available at:
```
https://github.com/ggml-org/llama.cpp
```

When you start llama-server, set a higher context size than the default 4096. Try 16000 or higher to start.

---

## FIM-capable LLMs

Below is an incomplete list of LLMs that use the FIM control tokens that FIMpad is configured to use by default.

---

Granite 4.0 H Small, a 32B MoE, is available at:
```
https://huggingface.co/ibm-granite/granite-4.0-h-small-GGUF/tree/main
```

Granite 4.0 H Tiny, a 7B MoE, is available at:
```
https://huggingface.co/ibm-granite/granite-4.0-h-tiny-GGUF/tree/main
```

Qwen 3 Coder 30B A3B Instruct, an MoE, is available at:
```
https://huggingface.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF/tree/main
```

---

If you have a model that is capable of FIM, but uses unusual FIM control tokens, you can set the FIM tokens in the FIMpad settings window.

If you have a model that does not have FIM control tokens, you can still use FIMpad for completion. To do this, set the FIM tokens in the FIMpad settings window to empty strings. Then only the prefix will be sent to the LLM server. With the FIM tokens set to empty strings, you can even do system/user/assistant chat with instruct models, if you put the chat template role tags in the prefix text that you send to the model.

If you ever want to check if your suffix is actually being sent to the LLM server, check the log by pressing Alt+, (or use the menu entry at `AI -> Show Log`.) The logged events are one JSON object per generation. Log events have a "mode" name that will have value of either "completion generation" or "FIM generation". Additionally, completion generation events will not have a "suffix" name or associated value.

---

## The Library menu

The rightmost menu in FIMpad is the Library menu. The Library menu contains documentation, chat starters, public domain books, and all of the examples that you will find in this README. When you select something in the Library menu, it opens as a new tab in FIMpad. The files in the Library menu are all .txt and .md files that are bundled with FIMpad.

You will probably find it easier to load the examples below via the Library menu, since copying some of them from this webpage can give you leading spaces from the block quote formatting. Find the examples in `Library -> README Examples`.

---

## Example 1: A simple completion

FIMpad uses tags enclosed in triple brackets to differentiate FIMpad tags from the rest of the text. There are four classes of tags. We start with the most important type of tag: the FIM tag. 

See how a FIM tag looks before you execute it below.

> Four score and seven[[[50]]]

Here, 50 is the max number of tokens that the LLM will be allowed to generate when the FIM tag is executed.

Execute the FIM tag by placing the caret within the FIM tag, or immediately at the end of the tag after the last closing bracket.

The caret is the blinking marker for the position within the text that you are typing. (Many also call this a cursor, but in FIMpad the term caret is used to disambiguate between the text cursor and the mouse cursor.)

With the caret within or immediately after the FIM tag, execute the tag by pressing Alt+[ (or select `AI -> Generate` in the menu.) The FIM tag will be deleted, and FIMpad will send the text before the tag to the LLM server as prefix text, and then the LLM server will respond with 50 or fewer tokens that the LLM deems most likely to appear after the prefix. The response will be streamed into the text editor starting at the location where the FIM tag was before it was deleted. When the response completes, it will look something like this:

> Four score and seven years ago our fathers brought forth on this continent, a new nation, conceived in Liberty, and dedicated to the proposition that all men are created equal.
> 
> Now we are engaged in a great civil war, testing whether that nation, or any nation so conceived

There is variability in LLM output, so your results may not look exactly like those above.

---

## Example 2: Fill in the middle.

In the prior example there was no text after the FIM tag, so it was generated as a completion. But if you are using an LLM capable of FIM (Fill In the Middle), and if you have the FIM tokens for it set correctly in the FIMpad settings window, you will get a FIM generation when you execute a FIM tag and there is text after the tag.

With FIM tags, text that appears before the FIM tag is *prefix*. Text that appears after the tag is *suffix*.

Let's look at an example that generates a Bash script. It uses a technique that you might call "declare what follows." In the prefix, describe what you want to be generated after the tag. Then optionally give a suffix that is something you would expect to see come after it. See below, before the FIM tag is executed.

```
#!/bin/bash

# This script takes a path to a video file ($1) and uses FFMPEG,
# which is in the PATH, to downscale the video to 480p and
# render it as an MP4 with AAC audio, with compression for
# both video and audio that targets small file size with not
# too much loss of quality. The file name of the rendered video
# will be the base name of the input file with "_compressed"
# appended before the extension. The final output 
# resolution dimensions will be divisible by two without
# remainder.
[[[400;temp("0.7");top_p("0.95")]]]
echo "The file has been rendered successfully."
exit 0
```

Below is the result of the above, after executing the tag, using Granite Small Base:

```
#!/bin/bash

# This script takes a path to a video file ($1) and uses FFMPEG,
# which is in the PATH, to downscale the video to 480p and
# render it as an MP4 with AAC audio, with compression for
# both video and audio that targets small file size with not
# too much loss of quality. The file name of the rendered video
# will be the base name of the input file with "_compressed"
# appended before the extension. The final output 
# resolution dimensions will be divisible by two without
# remainder.

echo "Starting compression."
ffmpeg -i "$1" -vf scale=-2:480 -c:v libx264 -crf 23 -preset veryfast -c:a aac -b:a 128k "${1%.*}_compressed.mp4" -hide_banner
echo "The file has been rendered successfully."
exit 0
```

The LLM generated fewer than the given max of 400 tokens, because fewer than 400 tokens were needed to appropriately fill the gap between prefix and suffix.

If you wanted a script that paid more attention to avoiding errors, you could start the prefix with something like this:

```
#!/usr/bin/env bash
set -euo pipefail
```

Careful Bash script writers will often start out like that, instead of starting with `#!/bin/bash`.

You may have noticed that the FIM tag used in this example is more complicated than the FIM tag used in Example 1. FIM tags have optional functions that can be used to control what FIMpad does when a FIM tag is executed. The two FIM tag functions used here are `temp()` and `top_p()`. They control the Temperature and Top P settings that the LLM server uses during generation. In the FIMpad settings window you can set the default Temperature and Top P values, but the `temp()` and `top_p()` functions provide per-execution overrides of the default values.

Let's take a closer look at this tag.

```
[[[400;temp("0.7");top_p("0.95")]]]
```

Semicolons separate the parts of a FIM tag, and whitespace is ignored before and after the parts, so you can also write them like this:

```
[[[400; temp("0.7"); top_p("0.95")]]]
```

Or in multi-line blocks, like this:

```
[[[
400;
temp("0.7");
top_p("0.95");
]]]
```

Or this:

```
[[[
    400;
    temp("0.7");
    top_p("0.95");
]]]
```

The last semicolon before the end of the tag is optional. Double quotes surrounding the function arguments are required. When a FIM tag function takes more than one argument, commas separate those. The first part of a FIM tag must always be an integer representing max tokens for that generation.

---

## Example 3: Chat with a base model

You can write a few lines to establish context and get a little chat going. It is best to use labels and write in a structured way, so that the LLM has a predictable format to follow. In the following example there is regular alternation of speakers. I'm going to chat as Chauncey and have the LLM be Fiona. Here is the setup before the first generation:

> Chauncey: I have been told that you are very intelligent and very creative.
>
> Fiona: True. I am both. Very.
>
> Chauncey: Good, I have a project which requires your assistance.
>
> Fiona: [[[250; stop("Chauncey: "); append("\n\nFiona: ")]]]

The first function in the FIM tag is `stop()`. This function takes one or more arguments representing stop sequences. A *stop sequence* is a string that, if generated by the LLM, ends generation immediately at that point. So the last thing that gets inserted into the text editor is "Chauncey: ", with the space at the end, so I can just start typing what I want to say after the LLM generates what Fiona says. If I didn't use stop, the LLM would likely keep going and write dialogue for Chauncey, which I don't want in this case since I will be speaking for Chauncey.

If more than one stop sequence is given, like this:

```
[[[250; stop("Chauncey: ","Narrator: ")]]]
```

then the model will stop at the first stop sequence that the LLM generates, if any. If neither of the stop sequences are generated, the LLM will stream text until it finishes or hits max tokens. But in the example above, since I establish a regular pattern of speaker label alternation, "Chauncey: " is very likely to appear when the LLM completes this prefix.

(There is another FIM tag function called `chop()` that does the same thing as `stop()`, except it discards the stop sequence, so that last thing streamed into the text editor is the last character that was generated before the stop sequence.)

The other function in the tag is `append()`. This function appends text after the LLM's generation. I'm using it to append two newlines and then the "Fiona: " label, so I won't need to type Fiona's label every turn. I can just click after the "Chauncey: " label, type my message, then click after the "Fiona: " label and press Alt+] (or select `AI -> Repeat Last FIM` in the menu) to repeat the last executed FIM tag at the current position of the caret. If you ever want to modify the last FIM tag before executing it, you can press Alt+' (or select `AI -> Paste Last FIM Tag` in the menu) and the last FIM tag that you executed will be pasted at the current position of the caret.

Anyway, let's see how this example plays out after generation.

> Chauncey: I have been told that you are very intelligent and very creative.
>
> Fiona: True. I am both. Very.
>
> Chauncey: Good, I have a project which requires your assistance.
>
> Fiona:  Yes, I like projects. What is the project?
>
> Chauncey: 
>
> Fiona: 

From this point you can keep chatting with Fiona in a way that does not require typing more labels and tags.

---

## Example 4: Write a story

One strategy for writing a story with FIMpad is to start with a sentence that you don't know how to finish.

> It was a dark and stormy midnight at the zoo, and the scene in the night shift employee break room near the gorilla enclosure was as boring as ever; however, [[[120]]]

after generation:

> It was a dark and stormy midnight at the zoo, and the scene in the night shift employee break room near the gorilla enclosure was as boring as ever; however, 5 minutes later, all the employees would be having a near heart-attack and all the zoo animals would be wondering what the hell just happened.
>
>The zoo had recently acquired a new gorilla, named George, who had quickly become a favorite among visitors and staff alike. George was a massive silverback gorilla with a personality that was as large as his body. He was known for his playful antics, his love of bananas, and his uncanny ability to mimic human behavior.
>
>One night, a new night shift employee named Jake was on duty. Jake was a young man in his early twenties,

I don't want George to be known for his playful antics, so I estimate the token length of the description of something else that he could be known for at about 5 tokens, and I do this:

> It was a dark and stormy midnight at the zoo, and the scene in the night shift employee break room near the gorilla enclosure was as boring as ever; however, 5 minutes later, all the employees would be having a near heart-attack and all the zoo animals would be wondering what the hell just happened.
>
> The zoo had recently acquired a new gorilla, named George, who had quickly become a favorite among visitors and staff alike. George was a massive silverback gorilla with a personality that was as large as his body. He was known for his [[[5]]], his love of bananas, and his uncanny ability to mimic human behavior.
>
> One night, a new night shift employee named Jake was on duty. Jake was a young man in his early twenties,

After I generate I have this:

> It was a dark and stormy midnight at the zoo, and the scene in the night shift employee break room near the gorilla enclosure was as boring as ever; however, 5 minutes later, all the employees would be having a near heart-attack and all the zoo animals would be wondering what the hell just happened.
>
> The zoo had recently acquired a new gorilla, named George, who had quickly become a favorite among visitors and staff alike. George was a massive silverback gorilla with a personality that was as large as his body. He was known for his sense of humor, his love of bananas, and his uncanny ability to mimic human behavior.
>
> One night, a new night shift employee named Jake was on duty. Jake was a young man in his early twenties,

Now let's provide a suffix after this next tag to drive Jake's paragraph towards impending conflict. The suffix doesn't even need to be good, it can be deleted after, it just provides a target state for the story so that the LLM interpolates plot between the prefix and the suffix.

> It was a dark and stormy midnight at the zoo, and the scene in the night shift employee break room near the gorilla enclosure was as boring as ever; however, 5 minutes later, all the employees would be having a near heart-attack and all the zoo animals would be wondering what the hell just happened.
>
> The zoo had recently acquired a new gorilla, named George, who had quickly become a favorite among visitors and staff alike. George was a massive silverback gorilla with a personality that was as large as his body. He was known for his sense of humor, his love of bananas, and his uncanny ability to mimic human behavior.
>
> One night, a new night shift employee named Jake was on duty. Jake was a young man in his early twenties, [[[120]]]
>
> Because of that, Jake started to get very nervous.

after generation:

> It was a dark and stormy midnight at the zoo, and the scene in the night shift employee break room near the gorilla enclosure was as boring as ever; however, 5 minutes later, all the employees would be having a near heart-attack and all the zoo animals would be wondering what the hell just happened.
>
> The zoo had recently acquired a new gorilla, named George, who had quickly become a favorite among visitors and staff alike. George was a massive silverback gorilla with a personality that was as large as his body. He was known for his sense of humor, his love of bananas, and his uncanny ability to mimic human behavior.
>
> One night, a new night shift employee named Jake was on duty. Jake was a young man in his early twenties, who had just started working at the zoo to make some extra money while he finished his degree in biology. Jake was a bit of a nervous wreck, and he was always on edge when he was on duty.
>
> That night, as Jake was sitting in the break room eating his dinner and scrolling through his phone, he heard a strange noise coming from the gorilla enclosure. At first, he thought it was just the wind, but then he heard it again, and it sounded like someone was laughing.
>
> Jake's heart started to race as he stood up and walked towards the enclosure. As he got closer,
>
> Because of that, Jake started to get very nervous.

The "Jake's heart" paragraph near the end was cut off by the max token limit of 120 that I gave. Let's remove the suffix text that I wrote earlier and complete that paragraph.

We'll use `stop()` below, with multiple stop sequences, to make sure that generation stops cleanly at the end of a paragraph, by stopping at any point where there is a newline following a period, a question mark, or an exclamation point.

> It was a dark and stormy midnight at the zoo, and the scene in the night shift employee break room near the gorilla enclosure was as boring as ever; however, 5 minutes later, all the employees would be having a near heart-attack and all the zoo animals would be wondering what the hell just happened.
>
> The zoo had recently acquired a new gorilla, named George, who had quickly become a favorite among visitors and staff alike. George was a massive silverback gorilla with a personality that was as large as his body. He was known for his sense of humor, his love of bananas, and his uncanny ability to mimic human behavior.
>
> One night, a new night shift employee named Jake was on duty. Jake was a young man in his early twenties, who had just started working at the zoo to make some extra money while he finished his degree in biology. Jake was a bit of a nervous wreck, and he was always on edge when he was on duty.
>
> That night, as Jake was sitting in the break room eating his dinner and scrolling through his phone, he heard a strange noise coming from the gorilla enclosure. At first, he thought it was just the wind, but then he heard it again, and it sounded like someone was laughing.
>
> Jake's heart started to race as he stood up and walked towards the enclosure. As he got closer, [[[55;stop(".\n","?\n","!\n")]]]

after generation:

> It was a dark and stormy midnight at the zoo, and the scene in the night shift employee break room near the gorilla enclosure was as boring as ever; however, 5 minutes later, all the employees would be having a near heart-attack and all the zoo animals would be wondering what the hell just happened.
>
> The zoo had recently acquired a new gorilla, named George, who had quickly become a favorite among visitors and staff alike. George was a massive silverback gorilla with a personality that was as large as his body. He was known for his sense of humor, his love of bananas, and his uncanny ability to mimic human behavior.
>
> One night, a new night shift employee named Jake was on duty. Jake was a young man in his early twenties, who had just started working at the zoo to make some extra money while he finished his degree in biology. Jake was a bit of a nervous wreck, and he was always on edge when he was on duty.
>
> That night, as Jake was sitting in the break room eating his dinner and scrolling through his phone, he heard a strange noise coming from the gorilla enclosure. At first, he thought it was just the wind, but then he heard it again, and it sounded like someone was laughing.
>
> Jake's heart started to race as he stood up and walked towards the enclosure. As he got closer, he could hear the laughter more clearly, and it sounded like it was coming from inside the enclosure.

Keep in mind that when you get a generation that you don't like, you can simply press Alt+U to undo the generation. Then press Alt+[ to generate again. Because of the semi-random variation in LLM responses, you can step through dozens of variations until you land on one that you like.

---









