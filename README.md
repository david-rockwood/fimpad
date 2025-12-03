# FIMpad

FIMpad is a FIM-focused local LLM interface in the form of a tabbed GUI text editor.

---

https://github.com/user-attachments/assets/4a998eb3-a97a-4744-bc49-66a94b9f11a2

---

FIMpad is currently only tested on Linux, using llama.cpp's llama-server to serve LLMs.

If you’ve had success, or encountered issues, on other operating systems, please let me know. I aim to make FIMpad cross-platform in the future, and I’ve written the code with portability in mind.

---

## Overview

FIMpad is both an AI sandbox and a text editor. The editor is your interface to the LLM: AI text generation happens directly within regular text files, and sessions can be saved and resumed from those files. You can perform either completion or FIM (Fill-In-the-Middle) generation at any point in the text.

---

## Quick start

### Option 1 – Linux standalone binary (recommended on Linux)

1. Go to the **Releases** page on the FIMpad GitHub repo.

2. Download the latest Linux archive, for example:

```
fimpad-linux-v0.0.17.tar.gz
```

3. Extract it:

```
tar -xzf fimpad-linux-v0.0.17.tar.gz
```

This will give you a single executable file named `fimpad` in the current directory.

4. Make sure it’s executable (it usually is, but this won’t hurt):

```
chmod +x fimpad
```

5. Run FIMpad:

```
./fimpad
```

---

### Option 2 – Run from source (minimal Python install)

Requires **Python 3.10+** and a working C toolchain (your usual Python build environment).

```
git clone https://github.com/david-rockwood/fimpad.git
cd fimpad

# (Recommended) create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

# Install FIMpad with minimal runtime dependencies
pip install .
```

Then launch:

```
python3 -m fimpad
```

---

## The server

FIMpad requires a connection to an LLM server that provides an OpenAI-compatible endpoint. By default, FIMpad expects this endpoint at `http://localhost:8080`. This base URL can be changed in the FIMpad settings window.

Currently, FIMpad is only tested with `llama.cpp`’s `llama-server`. A recent build of `llama.cpp` is recommended, available at:
```
https://github.com/ggml-org/llama.cpp
```

When starting `llama-server`, use a context size larger than the default 4096. Try 32768.

---

## FIM-capable LLMs

Below is an incomplete list of LLMs that use the FIM control tokens that FIMpad is configured to use by default.

---

Qwen 3 Next 80B A3B Instruct, an MoE, is available at:

```
https://huggingface.co/bartowski/Qwen_Qwen3-Next-80B-A3B-Instruct-GGUF/tree/main
```

Qwen 3 Coder 30B A3B Instruct, an MoE, is available at:
```
https://huggingface.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF/tree/main
```

IBM Granite 4.0 H Small, a 32B MoE, is available at:
```
https://huggingface.co/ibm-granite/granite-4.0-h-small-GGUF/tree/main
```

IBM Granite 4.0 H Tiny, a 7B MoE, is available at:
```
https://huggingface.co/ibm-granite/granite-4.0-h-tiny-GGUF/tree/main
```

---

If you’re using a model with non-standard FIM control tokens, you can configure them manually in the FIMpad settings window.

If your model does not support FIM tokens at all, you can still use FIMpad for standard completion. To do so, set the FIM tokens in the settings to empty strings. This will cause FIMpad to send only the prefix text to the server. In this mode, you can also use instruction-tuned models with chat templates by typing role tokens (`<|im_start|>`, etc.) directly into your prefix. FIMpad has templates with role tokens already prepared at `Library → Chat Starters`.

To verify whether your suffix is being sent to the server, open the log via `Alt+L` (or `AI → Show Log`). Each generation event is logged as a JSON object with a `"mode"` field: either `"completion generation"` or `"FIM generation"`. Completion generations will not include a `"suffix"` field.

---

## The Library menu

The rightmost menu in FIMpad is the **Library** menu. It contains documentation, chat starters, and all examples included in this README. Selecting any item opens it as a new tab in FIMpad. All library items are bundled `.txt` and `.md` files.

You’ll likely find it easier to load examples from the Library menu than copying them directly from this web page, since web formatting often introduces unwanted leading spaces. Find the examples under:  
**Library → README Examples**

---

## Example 1: A simple completion

FIMpad uses triple-bracketed tags to distinguish FIMpad-specific instructions from regular text. There are four tag types—begin with the most important: the **FIM tag**.

Here’s how a FIM tag looks before execution:

> Four score and seven[[[50]]]

Here, `50` is the maximum number of tokens the LLM is allowed to generate.

To execute the tag:
1. Place the caret (cursor) **within** the FIM tag or **immediately after** the last closing bracket.
   *(In FIMpad, we use the term “caret” to distinguish the text cursor from the mouse cursor.)*
2. Press `Alt+G` (or select `AI → Generate` from the menu).

The FIM tag will be deleted, and FIMpad will send the text before the tag as prefix text to the server. The server will respond with up to 50 tokens deemed most likely to follow. The response is streamed into the editor at the former tag location.

After generation, the result may look like this:

> Four score and seven years ago our fathers brought forth on this continent, a new nation, conceived in Liberty, and dedicated to the proposition that all men are created equal.
> 
> Now we are engaged in a great civil war, testing whether that nation, or any nation so conceived

Note: LLM outputs vary. Your result may differ slightly.

---

## Example 2: Fill in the middle.

In the previous example, there was no text after the FIM tag—so it functioned as a completion. But with an FIM-capable model and properly configured FIM tokens, you can generate text *between* a prefix and a suffix.

Text before the tag = **prefix**  
Text after the tag = **suffix**

Here’s an example that generates a Bash script:

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

After generation (using Granite Small Base):

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

The model generated fewer than 400 tokens because fewer were needed to bridge the gap between prefix and suffix.

To improve robustness, you might start the script with:

```bash
#!/usr/bin/env bash
set -euo pipefail
```

This is a common practice among experienced Bash writers.

Notice that this FIM tag includes optional functions: `temp()` and `top_p()`. These override the default generation settings for this generation only.

---

## FIM Tag Syntax

FIM tags use semicolons to separate components. Whitespace is ignored before or after each part.

Example:
```
[[[400; temp("0.7"); top_p("0.95")]]]
```

You may format it across multiple lines for readability:

```
[[[
    400;
    temp("0.7");
    top_p("0.95");
]]]
```

The final semicolon before the closing brackets is optional. Double quotes around function arguments are required.

The first component must be an integer: the maximum number of tokens to generate.

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

(There is another FIM tag function called `chop()` that does the same thing as `stop()`, except it discards the stop sequence, so that the last thing streamed into the text editor is the last character that was generated before the stop sequence.)

The other function in the tag is `append()`. This function appends text after the LLM's generation. I'm using it to append two newlines and then the "Fiona: " label, so I won't need to type Fiona's label every turn. I can just click after the "Chauncey: " label, type my message, then click after the "Fiona: " label and press Alt+R (or select `AI -> Repeat Last FIM` in the menu) to repeat the last executed FIM tag at the current position of the caret. If you ever want to modify the last FIM tag before executing it, you can press Alt+P (or select `AI -> Paste Last FIM Tag` in the menu) and the last FIM tag that you executed will be pasted at the current position of the caret.

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

A powerful technique for writing fiction is to start with a sentence you don’t know how to finish.

> It was a dark and stormy midnight at the zoo, and the scene in the night shift employee break room near the gorilla enclosure was as boring as ever; however, [[[120]]]

After generation:

> It was a dark and stormy midnight at the zoo, and the scene in the night shift employee break room near the gorilla enclosure was as boring as ever; however, 5 minutes later, all the employees would be having a near heart-attack and all the zoo animals would be wondering what the hell just happened.
>
> The zoo had recently acquired a new gorilla, named George, who had quickly become a favorite among visitors and staff alike. George was a massive silverback gorilla with a personality that was as large as his body. He was known for his playful antics, his love of bananas, and his uncanny ability to mimic human behavior.
>
> One night, a new night shift employee named Jake was on duty. Jake was a young man in his early twenties,

You may dislike George being described as “playful.” So replace it with a FIM tag to refine:

> He was known for his [[[5]]], his love of bananas, and his uncanny ability to mimic human behavior.

Generate → result:

> He was known for his sense of humor, his love of bananas, and his uncanny ability to mimic human behavior.

Now, add a suffix to guide the next paragraph:

> One night, a new night shift employee named Jake was on duty. Jake was a young man in his early twenties, [[[120]]]
>
> Because of that, Jake started to get very nervous.

After generation:

> One night, a new night shift employee named Jake was on duty. Jake was a young man in his early twenties, who had just started working at the zoo to make some extra money while he finished his degree in biology. Jake was a bit of a nervous wreck, and he was always on edge when he was on duty.
>
> That night, as Jake was sitting in the break room eating his dinner and scrolling through his phone, he heard a strange noise coming from the gorilla enclosure. At first, he thought it was just the wind, but then he heard it again, and it sounded like someone was laughing.
>
> Jake's heart started to race as he stood up and walked towards the enclosure. As he got closer,
>
> Because of that, Jake started to get very nervous.

Notice the generation was cut off. Let’s delete the suffix and finish the paragraph cleanly by using `stop()` with sentence-ending delimiters:

> One night, a new night shift employee named Jake was on duty. Jake was a young man in his early twenties, who had just started working at the zoo to make some extra money while he finished his degree in biology. Jake was a bit of a nervous wreck, and he was always on edge when he was on duty.
>
> That night, as Jake was sitting in the break room eating his dinner and scrolling through his phone, he heard a strange noise coming from the gorilla enclosure. At first, he thought it was just the wind, but then he heard it again, and it sounded like someone was laughing.
>
> Jake's heart started to race as he stood up and walked towards the enclosure. As he got closer, [[[55;stop(".\n","?\n","!\n")]]]

Result:

> Jake's heart started to race as he stood up and walked towards the enclosure. As he got closer, he could hear the laughter more clearly, and it sounded like it was coming from inside the enclosure.

If you’re unsatisfied with a generation, press `Ctrl+Z` to undo, then `Alt+G` to retry. Due to LLM randomness, you can iterate through dozens of variations until you find the perfect one.

---

More to come later, we haven’t even covered context tags, config tags, and comment tags yet.
