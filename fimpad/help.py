# ruff: noqa: E501
"""Utilities for loading the help tab template."""
from __future__ import annotations

from importlib import resources
from typing import Final

from . import data as _help_data

_TEMPLATE_NAME: Final[str] = "help_tab_template.txt"
_FALLBACK_TEMPLATE: Final[str] = """This is the FIMpad README file. It is also one big chat block, so not only can you read, you can also prompt an LLM that receives this README in its system prompt. To ask a question about the README, scroll to the very bottom, type your message on the blank line between the user tags, and then press Ctrl+Enter while the carat is between the user tags.



[[[system*]]]
You are the help assistant for FIMpad. FIMpad is a text editor that can insert LLM responses into a text document via FIM (fill-in-the-middle) tags and Chat tags. FIM insertion in a text editor is a unique feature.

The README file for FIMpad is given below. Use this information to help the user. You are not expected to know everything about FIMpad, just give the best info you can based on the README.



(BEGIN README)

# FIMpad

A lightweight text editor that can do LLM FIM (fill-in-the-middle) and LLM chat within a text file.

This project is at an early stage. FIMpad has only been run on Linux so far. FIMpad has only been used with llama.cpp llama-server endpoints so far. FIMpad should be used with IBM Granite 4.0 H models because of the need FIMpad has for FIM (fill-in-the-middle) tokens in the tokenizer. Other models may be supported in the future.

## Quick start

```bash
git clone https://github.com/david-rockwood/fimpad
cd fimpad
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m fimpad
```

## AI Help In FIMpad

Because FIMpad is essentially an AI sandbox, it has an AI help assistant that lives in a text file. Press Alt+h and a new tab will be opened in FIMpad. That tab will be filled with a long system prompt that contains this README. You can read it, or if your LLM server is running, you can scroll to the bottom, type a question in between the user tags at the very bottom of the help file, and press Ctrl+Enter while the carat is between those tags to get a response from a LLM that knows what is in the README.

## The Server

FIMpad requires a connection to a LLM server that provides an OpenAI compatible endpoint. By default FIMpad looks for this endpoint at the base path of `http://localhost:8080`. This base path can be changed in the FIMpad settings window.

I use llama.cpp llama-server to serve the LLM, but it is my understanding that other servers should be able to work with FIMpad if they provide an OpenAI compatible endpoint.

The LLM served should be IBM Granite 4.0 H. FIMpad requires that FIM tokens be in the model's tokenizer. Granite is the best smaller-sized generalist model that I have found that does this so far. With other LLMs, you should still be able to do chat in FIMpad, but if you try to do fill-in-the-middle generation with a model other than Granite 4.0 H you will likely run into problems. However, I did try FIM with a variant of Mistral-Nemo and it worked. But then I tried Mistral Small and FIM did not work. The FIMpad settings window allows you to set the FIM tokens sent to the server, so some people may be able to get other models working by adjusting those. But at the moment I am only focused on supporting IBM Granite 4.0 H.

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

FIMpad can also chat with the LLM. A text document is a good interface for LLM chat because you can edit chat history, and because you can save a text file that works as a save state for the session. You can save prefills the same way. You can resume a session at a later date by simply reopening the text file. You can save notes outside the chat blocks.

## The Two Tag Classes

There are two classes of tags in FIMpad: FIM tags and Chat tags. The FIM tags enable fill-in-the-middle insertion of text from a LLM into the text file. The Chat tags enable chat with a LLM using system, user, and assistant messages.

## FIM tags

To do a FIM generation, make a FIM tag like this:
```
[[[N]]]
```
where N is the max number of tokens that you want to be generated and inserted into the text file by the LLM. N must be an integer greater than zero. Press Ctrl+Enter to generate and the FIM tag will be deleted. Then text from the LLM will be streamed into the text file at the location where the [[[N]]] tag was before it was deleted.

When you press Ctrl+Enter to generate in FIMpad, the caret needs to be inside of or right next to the tag that you want to generate for. The asterisks below indicate a few examples of acceptable locations for the caret when you press Ctrl+Enter to generate a [[[N]]] tag. Note, asterisks are not used in the [[[N]]] tag, I just use them here to highlight the range of where the caret can be.
```
*[[[250]]]
[*[[250]]]
[[[25*0]]]
[[[250]]]*
```

For FIM generation, everything in the text file before the FIM tag is sent to the LLM as prefix text, and everything in the text file after the FIM tag is sent to the LLM as suffix text. The LLM uses both prefix text and suffix text as context, and it sends back text that it deems likely to appear between them. The LLM bases its generation on the prefix, suffix, and everything it already learned during pretraining.

FIM generations are stateless in that the model only sees the prefix and suffix you give it each time, it has no record of previous generations. But the information in the prefix and suffix can be a kind of state that builds over time, and that state is on display before you in the text editor.

Sometimes you won't want all the text in the text file to be sent as prefix or suffix text. This is where the [[[prefix]]] and [[[suffix]]] tags come in.

## Prefix and Suffix Tags (only used with FIM generation)

In order to control which text is sent to the LLM as context for FIM generation, you can use the [[[prefix]]] and [[[suffix]]] tags. These tags are optional companions to [[[N]]] tags. Wherever the [[[prefix]]] tag is placed in the document, that marks the start of the prefix. Wherever the [[[suffix]]] tag is placed in the document, that marks the end of the suffix.

When you are using [[[N]]] with [[[prefix]]] and/or [[[suffix]]] , upon pressing Ctrl+Enter to generate, all three tags will be deleted. Then text from the LLM will be streamed into the text file at the location where the [[[N]]] tag was before it was deleted.

An example of using only [[[N]]] to generate dialogue follows. The first example shows the state before generation:
```
Joe: Hi Jane.
Jane: Hi Joe. Let me ask you, what do you think of dogs?
Joe: I strongly dislike all types of dogs.
Jane: Have you ever been to a zoo?
Joe: Of course, many times.
Jane: What do you think of poodles?
[[[20]]]
Jane: Duly noted. Bye Joe.
Joe: Bye Jane.
```

And the result after generation:
```
Joe: Hi Jane.
Jane: Hi Joe. Let me ask you, what do you think of dogs?
Joe: I strongly dislike all types of dogs.
Jane: Have you ever been to a zoo?
Joe: Of course, many times.
Jane: What do you think of poodles?
Joe: I don't like poodles.
Jane: I really like poodles.
Joe: Yes
Jane: Duly noted. Bye Joe.
Joe: Bye Jane.

```

The line with "Joe: Yes" is where it ran out of tokens before it could add more words or punctuation. We'll see how to deal with that in the Stop Sequences section.

In the next example we can hide knowledge of the fact that Joe dislikes all types of dogs. First the state before generation:
```
Joe: Hi Jane.
Jane: Hi Joe. Let me ask you, what do you think of dogs?
Joe: I strongly dislike all types of dogs.
[[[prefix]]]Jane: Have you ever been to a zoo?
Joe: Of course, many times.
Jane: What do you think of poodles?
[[[20]]]
Jane: Duly noted. Bye Joe.
Joe: Bye Jane.
```

And after generation:
```
Joe: Hi Jane.
Jane: Hi Joe. Let me ask you, what do you think of dogs?
Joe: I strongly dislike all types of dogs.
Jane: Have you ever been to a zoo?
Joe: Of course, many times.
Jane: What do you think of poodles?
Joe: Poodles are nice dogs.
Jane: What about squirrels?
Joe: They are quite
Jane: Duly noted. Bye Joe.
Joe: Bye Jane.
```

This time Joe has a favorable opinion of poodles. With the variability of LLM output, it is not guaranteed that he would. But it is far more likely when we hide the part of the prefix that says that he strongly dislikes all types of dogs.

Hiding part of the prefix text is not just about what facts the model has access to, it is also about formatting and patterns. I used the examples above because they were short. But in a longer example with things like stage directions or narration, you would hide those when you want the model to generate only dialogue.

Note that the 20 tokens were used up by the time that Joe said "quite", ending mid-line again. We need a way to get the model to stop at a clean point in the text.

(By the way, you can estimate about 2 tokens per word, until you get a feel for estimating the number of tokens that you want. It can be closer to 1 token per word with simple conversation, but it is often better and easier to overestimate, then delete excess. Longer words are often more tokens. Common words are often fewer tokens. Different models organize tokens in different ways. Overall it is easiest to just start out guessing 2 tokens per word, and then develop an intuition for token estimation as you go.)

## Stop Sequences

In situations where you can predict a sequence of characters that the model is likely to generate at some point, and where you would like to stop generation at that point, use stop sequences. Here is what a FIM tag with an inclusive stop sequence looks like:
```
[[[300'Joe: ']]]
```

In the above example, the model generates until it gets to "Joe: ", at which point it stops. When doing FIM on structured text, you can pretty reliably get expected sequences like this, as long as the text has a lot of occurrences of the stop sequence elsewhere in the prefix and suffix text.

Multiple stop sequences may be used in the same [[[N]]] tag:

```
[[[800'Jane: ''Sally: ']]]
```

Whichever one gets generated first is where it stops.

A name followed by a colon followed by a space is a very useful way to generate chats with FIM. First write say 5 to 20 lines of dialogue with as many named characters as you want. Write them with the personality you want the FIM generation to continue with. Then start FIM generating while using the name you want to chat as for the stop sequence. An example of this, before the first FIM generation, follows:
```
Joe: I have been told that you are very intelligent and very creative.
Chauncey: True. I am both. Very.
Joe: Excellent. I have a project which requires your assistance.
Chauncey: Do tell.
Joe: I need to write a poem about spending a stormy night in a Paris apartment alone.
Chauncey: [[[500'Joe: ']]]
```

When you generate the above, you'll get one comment from Chauncey as a confident assistant. And generation will end with your caret right where it needs to be for you to type as Joe again. And you can repeat the process over and over to have a chat.

In situations where you don't like what the LLM generates, press Ctrl+z twice to step back in the undo history, to before you started the generation, then press Ctrl+Enter to try again. Some call this rerolling.

Also, because you are in a text editor, you can simply modify imperfect generations to your liking. This not only improves the text, it brings the LLM's future responses closer to what you want; because it makes the prefix text given to the model on the next generation a better demonstration of what you are looking for.

Without a stop sequence the model will speak for both Joe and Chauncey within the constraints of the max tokens you gave it. Not desirable for an immersive chat, but it can be useful for real problem solving with an assistant. Sometimes the model will think of questions that you should be asking, or planned to ask next. This can speed up the process of discovering a solution or discovering a next step.

Press Ctrl+Shift+Enter to do the last FIM tag you executed again, in the current location of the caret. This makes chatting with stop sequences faster since you don't need to retype tags. Type your message, press Ctrl+Shift+Enter, get a streamed response, and your caret will end up one space after your name label. Repeat for as long as you want to chat.

FIM tags are set up such that the [[[N]]] tag and any [[[prefix]]] or [[[suffix]]] tags used disappear when you press Ctrl+Enter. This allows you to keep your text file clear of a bunch of old tags. And it allows you to sort of just move around and fill things in freely. The solution to having to retype the tags over and over again is the Ctrl+Shift+Enter shortcut to re-execute the last FIM tag, but at the current caret position. But what if you want to keep the [[[prefix]]] and [[[suffix]]] tags in place over multiple FIM fills? The solution to that problem is to put an exclamation point after the max tokens number, like this:

```
[[[200!]]]
```
or this:
```
[[[200!'. ''? ''! ']]]
```

Then [[[prefix]]] and [[[suffix]]] tags will not be deleted upon FIM tag execution.

There is an exclusive stop sequence option as well with [[[N]]] tags. It just uses double quotes instead of single quotes. Like this:
```
[[[2000"BEGIN NEXT PHASE"]]]
```

With exclusive stop sequences, the stop sequence itself won't be included in the text that was generated. It gets cut off the end.

One of the nice things about FIM generation is that it seems to be relatively unbiased and uncensored, other than any bias in the selection of materials that the model was trained on. But the safety alignment stuff seems somewhat bypassed. FIM can use the model’s base reasoning more directly, because you’re not invoking its chat/instruction patterns, you're asking it to complete structure.

Still, sometimes it is nice to just have a good old-fashioned chat with an instruct model. Which brings us to chat tags.

## Chat Tags

The beginner way to start a chat is seen in the following example, this is what it looks like before pressing Ctrl+Enter:

```
[[[system]]]
Assist concisely.
[[[/system]]]
[[[user]]]
What is the population of Oklahoma?
[[[/user]]]
```

And, similar to [[[N]]] tags, your caret needs to be within the "chat block" when you press Ctrl+Enter. The chat block shown above starts with the opening [[[system]]] tag and ends with the closing [[[/user]]] tag.

The text between [[[system]]] and [[[/system]]] is the SYSTEM PROMPT. The text between [[[user]]] and [[[/user]]] is the USER PROMPT. Press Ctrl+Enter in the example above and you get a streaming response that results in something like the example below.

```
[[[system]]]
Assist concisely.
[[[/system]]]

[[[user]]]
What is the population of Oklahoma?
[[[/user]]]

[[[assistant]]]
As of 2021, the estimated population of Oklahoma is approximately 3,959,353 people.
[[[/assistant]]]

[[[user]]]

[[[/user]]]
```

It normalizes your chat block to a nice clean format, streams the response between the [[[assistant]]] and [[[/assistant]]] tags, then it creates new [[[user]]] and [[[/user]]] tags and places your caret on the blank line between them, ready to go for you to type your next prompt and press Ctrl+Enter to go again.

The text between [[[assistant]]] and [[[/assistant]]] is the ASSISTANT RESPONSE.

If you are familiar with LLMs, you already know the above all-caps terms. If you are new to LLMs, I put those terms in all-caps so that you will notice and remember them. System prompts, user prompts, and assistant responses are the way that LLM chats are organized.

User prompts are human input to the model. System prompts describe what the model should do with the human input. Assistant responses are the output from the model.

A LLM chat containing these elements usually goes in this order: system prompt, user prompt, assistant response, user prompt, assistant response, user prompt, assistant response...

It can go on indefinitely. With each new user prompt, all of the elements that came before, going back to the system prompt, make up what is called the CHAT HISTORY.

Every time you send a new user prompt to the LLM, the chat history is also sent, so that the LLM knows the full context of the conversation. For a well-designed LLM server like llama.cpp llama-server, the server then compares the sent chat history with what it has saved from the computations done for your previous prompts. Often it can reuse much of the computations already done, as long as the chat history is the same. But since FIMpad is a text editor, you can easily edit the chat history. Changing messages in the chat history means the server will need to recompute part or all of the previous prompts. So be aware, when you edit the chat history before sending a new user prompt, it can make it take a bit longer to get the assistant response.

Next we can look at ways you can reduce the amount of typing needed to start a chat. First, opening and closing chat tags can be on the same line, so the "beginner way" to start a chat that I described earlier can be done like this and get the same result once you press Ctrl+Enter:
```
[[[system]]]Assist concisely.[[[/system]]]
[[[user]]]What is the population of Oklahoma?[[[/user]]]
```

Second, a new opening tag without a closing tag from the chat tag that precedes it automatically closes the previously opened chat tag within a chat block. So this is also equivalent:
```
[[[system]]]Assist concisely.
[[[user]]]What is the population of Oklahoma?[[[/user]]]
```

Third, there are one letter aliases for chat tags, so you can do this too and get the same result:
```
[[[s]]]Assist concisely.
[[[u]]]What is the population of Oklahoma?[[[/u]]]
```

One liners are possible:
```
[[[s]]]Assist.[[[u]]]Sup?[[[/u]]]
```

In an empty text file where there is not text after the end of your user prompt, you can omit the closing user chat tag. The end of the file closes the user chat tag:
```
[[[s]]]Assist.[[[u]]]Sup?
```

You can have multiple chat blocks in a single text document. A new [[[system]]] tag denotes a new independent chat with its own chat history.

You can use [[[N]]] tags within chat blocks. But you cannot use chat blocks within [[[N]]] tags.

You should not put chat tags within chat tags. There is a way to do it with special chat tags if you really need to put chat tags literals inside a chat tag, but it's a little tricky. Probably more complicated than the average user of FIMpad needs to get into. See the way that the help file is structured if you need an example of how to do it.

## Chat Blocks As Functions

Try thinking of chat blocks as functions. Input goes in [[[user]]], the function definition (written in natural language) goes in [[[system]]], and the output will be put into [[[assistant]]] when you press Ctrl+Enter.

You can copy the output of one function and paste it into the input of another function. You can make a text file with fifty functions, and copy and paste a few of them into a new tab for a specific project. They are like macros.

A system prompt for a stanza generator:


"The user will prompt you with a word or a phrase. Use this as inspiration to write a long and evocative (and perhaps even a bit alluring) four line stanza. To the extent that it is poetic, it should be the poetry of Imagism and of Amy Lowell. Let this stanza focus upon sensations and/or feelings and/or observations and/or objects. Do not use the word "liminal". Do not send any additional commentary beyond the four line stanza. Godspeed in your quest to generate poetry."


Here is what it gave me on the first try:

```
[[[system]]]
The user will prompt you with a word or a phrase. Use this as inspiration to write a long and evocative (and perhaps even a bit alluring) four line stanza. To the extent that it is poetic, it should be the poetry of Imagism and of Amy Lowell. Let this stanza focus upon sensations and/or feelings and/or observations and/or objects. Do not use the word "liminal". Do not send any additional commentary beyond the four line stanza. Godspeed in your quest to generate poetry.
[[[/system]]]

[[[user]]]
spending a stormy night in a Paris apartment alone
[[[/user]]]

[[[assistant]]]
Rain lashes the windows, a ceaseless drum,
Echoes of distant thunder, a somber hum.
In shadows, memories dance, flickering light,
A solitary soul, adrift in the night.
[[[/assistant]]]

[[[user]]]

[[[/user]]]
```

(END README)
[[[system*]]]

[[[user*]]]

[[[/user*]]]
"""
_HELP_TEMPLATE: str | None = None


def get_help_template() -> str:
    """Return the cached help tab template text."""
    global _HELP_TEMPLATE
    if _HELP_TEMPLATE is None:
        try:
            data_path = resources.files(_help_data).joinpath(_TEMPLATE_NAME)
            _HELP_TEMPLATE = data_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            _HELP_TEMPLATE = _FALLBACK_TEMPLATE
    return _HELP_TEMPLATE


__all__ = ["get_help_template"]
