# FIMpad

A text editor that can do Fill-In-the-Middle (FIM) text generation within a text file.

The first release will likely be in December 2025.

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

FIMpad is an AI sandbox and a text editor. The text editor is the interface to the LLM. AI workflows live in regular text files, and sessions can be saved to and resumed from a text file. You can do Fill-In-the-Middle (FIM) generation at any point in a text file. FIM generation is a versatile, powerful, and quick way to help with story writing and coding, among many other things.

---

## The server

FIMpad requires a connection to a LLM server that provides an OpenAI compatible endpoint. By default FIMpad looks for this endpoint at the base path of `http://localhost:8080`. This base path can be changed in the FIMpad settings window.

A recent build of llama.cpp llama-server is recommended, available at:
```
https://github.com/ggml-org/llama.cpp
```
When you start llama-server, set a higher context size than the default 4096. Try 16000 to start. Smaller runs faster, larger allows for longer documents and chats. Larger requires more RAM with CPU inference, or more VRAM with GPU inference. The max context size for IBM Granite 4.0 H is 131072.

---

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

---

## Understanding FIMpad’s tag tystem

FIMpad adds a small, lightweight “language” on top of plain text so you can run FIM completions directly inside your documents.
Everything happens through **tags**, which are little blocks of text surrounded by:

```
[[[ ... ]]]
```

---

## What tags are in FIMpad

A tag is a short instruction you place inside your document that tells FIMpad to do something:

* Generate text
* Run a multi-step workflow
* Mark where the “prefix” or “suffix” of a context should be
* Add invisible annotations
* Or just store notes that the model should not see

Tags look like this:

```
[[[something here]]]
```

The **first character after `[[[`** tells FIMpad what *kind* of tag it is.

---

## The Four Tag Types

### **FIM Tags: “Generate something here”**

These begin with a digit:

```
[[[200]]]
```

And they can have optional functions:

```
[[[200; temp("0.9")]]]
```

A FIM tag is a tiny script:

1. The number (`200`) says **how many tokens** the model may generate.
2. After that you can optionally write a sequence of **functions** (like `stop("END")` or `append("\n")`) that tell FIMpad how to configure the model and how to post-process the output.

Think of a FIM tag as:

> “Take the surrounding text (between prefix and suffix tags), call the model, generate up to N tokens, then apply these rules to the result.”

A FIM tag runs **right where it sits** in the document, and the generated text appears there.

---

### **Sequence Tags: “Run several named steps in order”**

These begin with a double quote:

```
[[[
  "step1";
  "step2";
  "step3";
]]]
```

A sequence tag doesn’t contact the model itself.
Instead, it tells FIMpad:

> “Look up the FIM tags named `step1`, then `step2`, then `step3`, and run them in that order.”

This is how you build **multi-step workflows** — like a pipeline where each FIM tag mutates the document for the next step.

---

### **Prefix/Suffix Tags: “Define what text the model will see”**

These use a word:

```
[[[prefix]]]
... some text ...
[[[suffix]]]
```

Prefix/suffix tags carve out the **context window** that a nearby FIM tag will use. Whatever is between the nearest prefix and suffix tags is what the model sees. If no prefix or suffix tags are used, the model sees everything in the file that isn't a tag.'

There are *soft* tags (`prefix`/`suffix`) and *hard* tags (`PREFIX`/`SUFFIX`):

* **Soft** ones auto-delete after use
* **Hard** ones stay permanently

Soft tags make it easy to design workflows that progressively consume boundaries.

Hard tags are good for long-lived structure, like chapter markers.

You do *not* need prefix/suffix tags for simple completions — but once you start doing multi-step processing, they become very powerful.

---

### **Comment Tags: “Notes the model can’t see”**

These start with `(`:

```
[[[(This is a note to myself; the model will never see it.)]]]
```

Comment tags are:

* Visible to **you**
* Invisible to **the model**
* Never auto-deleted
* Never affect context boundaries

They’re ideal for instructions, reminders, metadata, or debugging notes embedded inside the document.

---

## How FIMpad Decides What Context to Send to the Model

Whenever you execute a FIM tag:

1. FIMpad searches **backwards** from the tag to find the nearest `prefix` or `PREFIX`.
2. Then it searches **forward** to find the nearest `suffix` or `SUFFIX`.
3. The model sees everything *between* those two boundaries.
4. Comment tags inside that region are stripped out before sending to the model.
5. After generation:

   * **Soft** prefix/suffix tags that were used are automatically deleted.
   * **Hard** tags remain.

Simple mental model:

> FIM tags generate.
> Prefix/suffix tags define what they see.
> Sequence tags run several named FIM tags in a row.
> Comment tags are invisible to the model.

---

## Why This Tag System Exists

FIMpad is built around **Fill-In-the-Middle (FIM)**: generation that happens *between* a prefix and a suffix, rather than only after a prefix (like chat).

FIM is uniquely powerful when:

* You want the model to *rewrite* or *extend* a region of a document.
* You want multi-step pipelines (parse → analyze → rewrite → format).
* You want simple orchestration without writing Python code.
* You want deterministic stop conditions (`stop()`, `chop()`).
* You want natural-language reasoning steps in between.

The tag system gives you a structured way to use FIM inside a text editor, but without feeling like you’re writing a real programming language.

---

## Tag Summary

| Tag Type          | Looks Like                      | Purpose                                   |
| ----------------- | ------------------------------- | ----------------------------------------- |
| **FIM Tag**       | `[[[100; stop("END")]]]`        | Generate text here using FIM, with rules. |
| **Sequence Tag**  | `[[["step1"; "step2"]]]`        | Run named FIM tags in order.              |
| **Prefix/Suffix** | `[[[prefix]]]` / `[[[suffix]]]` | Define what text the model sees.          |
| **Comment Tag**   | `[[[(note)]]]`                  | Annotation; invisible to model.           |

---

## Using FIM tags

All tags in FIMpad are enclosed in triple brackets, in order to strongly differentiate tags from regular text. Of the the four classes of tags in FIMpad, FIM tags are the most important. A FIM tag marks the location in a text file where you want the LLM-generated text to be inserted. Below is an example of a simple FIM tag before insertion.

> Four score and seven [[[50]]]


The number 50 is enclosed in triple brackets. This FIM tag will stream a maximum of 50 tokens into the document. The tag will be deleted before streaming insertion. To execute a FIM tag, click inside the FIM tag such that the carat is within or directly adjacent to the FIM tag. Then press Ctrl+Enter (or use the menu entry at AI->Generate.) Below is an example of the result (although your result may not be an exact match due to the variability of LLM generation.).

> Four score and seven years ago, our fathers brought forth on this continent, a new nation, conceived in Liberty, and dedicated to the proposition that all men are created equal. Now we are engaged in a great civil war, testing whether that nation, or any nation so


Upon execution of the FIM tag, the tag is deleted from the document. All of the text between the beginning of the file and the location of the now-deleted FIM tag is considered prefix text. All of the text between the now-deleted FIM tag and the end of the file is considered suffix text. The prefix and the suffix are sent to the LLM server, and then the LLM server streams back the 50 (or fewer) tokens that the LLM deems most likely to appear between the prefix and the suffix.

In the above example, the document was empty past the FIM tag, so the LLM received an empty string for the suffix. In cases like this the streamed response is essentially a completion of the prefix.

Any valid tag that has an integer as the fourth character after the three opening bracket characters is a FIM tag.

---

## The FIM tag stop() function

Within FIM tags you can list functions that will modify what the FIM tag does. Below we have an example of an FIM tag without a function.

> John: Hello Jane.
>
> Jane: Hi John!
>
> John: Did you hear that our stupid economy collapsed?
>
> Jane: Yes. So I hear, so I hear.
>
> John: On the one hand, this will bring much suffering. On the other hand, I am eager to see a paradigm shift towards a more sensible allocation of resources.
>
> Jane: [[[75]]]

and, after execution:

> John: Hello Jane.
>
> Jane: Hi John!
>
> John: Did you hear that our stupid economy collapsed?
>
> Jane: Yes. So I hear, so I hear.
>
> John: On the one hand, this will bring much suffering. On the other hand, I am eager to see a paradigm shift towards a more sensible allocation of resources.
>
> Jane:  I feel the same way. I'm really looking forward to it.
>
> John: Me, too. But I'm afraid the government might intervene again to prevent the market from doing its job, and so prevent a recovery.
>
> Jane: Well, we will just have to stay alert and be prepared to act, should that happen.
>
> John: Yeah, that's the spirit.

The LLM generated multiple comments for John and Jane. In a situation where you want to chat, as John, with Jane, you want the generation to stop after Jane's comment, not John's, so that you can respond as John. And you want only one comment from Jane. And ideally the text inserted from the LLM will end exactly after "John: ", so that you can just start typing your response. You can set this up with the stop() function. The argument given to stop() is a stop sequence, which is a sequence of characters that tell FIMpad where to cut off the generation. If the stop sequence is generated by the LLM, the stop sequence characters are the last characters that will be inserted into the document for that FIM tag generation. See the example below, before generation.

> John: Hello Jane.
>
> Jane: Hi John!
>
> John: Did you hear that our stupid economy collapsed?
>
> Jane: Yes. So I hear, so I hear.
>
> John: On the one hand, this will bring much suffering. On the other hand, I am eager to see a paradigm shift towards a more sensible allocation of resources.
>
> Jane: [[[75;stop("John: ")]]]

and after generation:

> John: Hello Jane.
>
> Jane: Hi John!
>
> John: Did you hear that our stupid economy collapsed?
>
> Jane: Yes. So I hear, so I hear.
>
> John: On the one hand, this will bring much suffering. On the other hand, I am eager to see a paradigm shift towards a more sensible allocation of resources.
>
> Jane: 3D printers will make the scarcity of resources seem even more preposterous.
>
> John: 

It is not guaranteed that the LLM will generate a specific stop sequence, but it becomes likely when there is a well-established pattern of consistent repetition of that sequence in the prefix and/or the suffix.

In order to avoid retyping the FIM tag, you can press Ctrl+Shift+Enter (or use the menu entry at AI -> Repeat Last FIM) to execute the last executed FIM tag at the current carat position. And if you want to look at or modify the last executed FIM tag before you execute it, press Ctrl+Alt+Enter (or use the menu entry at AI -> Paste Last FIM Tag) and the last executed FIM tag will be pasted at the position of the carat.

So we now have a single comment from Jane, followed by a new line with the carat after the "John: " label. Then all you need to do in order to continue chatting with Jane is type your reply as John, then type the "Jane: " label on a new line, and then press Ctrl+Shift+Enter to generate the last executed FIM tag.

Still, if we are going to be talking with Jane for a while, it is annoying to have to type the "Jane: " label on a new line over and over again. We will resolve this in the next section.

---

## The FIM tag append() function

The append function simply adds some text onto the end of a streamed FIM insertion. See the example below, before generation.

> John: Hello Jane.
>
> Jane: Hi John!
>
> John: Did you hear that our stupid economy collapsed?
>
> Jane: Yes. So I hear, so I hear.
>
> John: On the one hand, this will bring much suffering. On the other hand, I am eager to see a paradigm shift towards a more sensible allocation of resources.
>
> Jane: 3D printers will make the scarcity of resources seem even more preposterous.
>
> John: That's an interesting angle.
>
> Jane: [[[75;stop("John: ");append("\nJane: ")]]]

and after generation:

> John: Hello Jane.
>
> Jane: Hi John!
>
> John: Did you hear that our stupid economy collapsed?
>
> Jane: Yes. So I hear, so I hear.
>
> John: On the one hand, this will bring much suffering. On the other hand, I am eager to see a paradigm shift towards a more sensible allocation of resources.
>
> Jane: 3D printers will make the scarcity of resources seem even more preposterous.
>
> John: That's an interesting angle.
>
> Jane: 3D printers can't be far off, it seems.
>
> John:
> 
> Jane: 

Now all you have to do is click after the "John: " label and type your response, then click after the "Jane: " label to place the carat, then press Ctrl+Shift+Enter.

---

## Writing a story with FIMpad

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
> The zoo had recently acquired a new gorilla, named George, who had quickly become a favorite among visitors and staff alike. George was a massive silverback gorilla with a personality that was as large as his body. He was known for his [[[5]]] , his love of bananas, and his uncanny ability to mimic human behavior.
>
>One night, a new night shift employee named Jake was on duty. Jake was a young man in his early twenties,

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

The stop() function can take multiple arguments that represent multiple stop sequences for a single FIM generation. The first of these stop sequences that is encountered during streaming is the one that terminates the FIM insertion. We'll use this below to make sure that generation stops clean at the end of a paragraph, by stopping at any point where there is a new line following a period, a question mark, or an exclamation point.

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

Keep in mind that when you get a generation that you don't like, you can simply press Ctrl+Z twice to step back through undo states until you are where you were before you generated the tag. Then press Ctrl+Enter to generate again. Some call this "rerolling", as in "taking another roll of the dice." Because of the semi-random variation in LLM responses, you can easily step through dozens of variations until you land on one that you like.

---




























