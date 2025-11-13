# FIMpad

A lightweight text editor that can do LLM FIM (fill-in-the-middle) and chat within a text file.

This project is at an early stage. FIMpad has only been run on Linux so far. FIMpad has only been used with llama.cpp llama-server endpoints so far. FIMpad only works with IBM Granite 4.0 H models because of the need FIMpad has for FIM (fill-in-the-middle) tokens in the tokenizer, and the lack (as far as I know) of very many instruct models that are set up for FIM.

## Quick start

```bash
git clone https://github.com/david-rockwood/fimpad
cd fimpad
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m fimpad
```

## The Server

FIMpad requires a connection to an LLM server that provides an OpenAI compatible endpoint. By default FIMpad looks for this endpoint at the base path of `http://localhost:8080`. This base path can be changed in the FIMpad settings window.

I use llama.cpp llama-server to serve the LLM, but it is my understanding that other servers should be able work with FIMpad if they provide an OpenAI compatible endpoint.

The LLM served must be IBM Granite 4.0 H. FIMpad requires FIM tokens be in the model's tokenizer. Granite is the best smaller-sized generalist model that I have found that does this so far. With other LLMs, you should still be able to do Chat in FIMpad, but if you try to do fill-in-the-middle generation with a model other than Granite 4.0 H you will likely run into problems.

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

Granite Small is 32B parameters. Granite Tiny is 7B parameters. Both are MoE models and run faster than dense models of the same size.

## Overview

With FIMpad, you can have AI sessions with a local LLM in a notepad-like text editor. You can do fill-in-the middle generation at any point in a text file. If you do fill-in-the-middle at the very end of a text file it works like completion. Fill-in-the-middle is a versatile and quick way to help with story writing and coding, among many other things.

FIMpad can also chat with the LLM. A text document is a good interface for LLM chat because you can edit chat history, and because you can save a text file that works as a save state for the session. You can save prefills the same way. You can resume a session at a later date by simply reopening the text file. You can save notes outside the chat tags.

## The Two Tag Classes

There are two classes of tags in FIMpad: FIM tags and Chat tags. The FIM tags enable fill-in-the-middle insertion of text from an LLM into the text file. The Chat tags enable chat with an LLM using system, user, and assistant messages.

## FIM tags

To do an FIM generation, make an FIM tag like this:
```
[[[N]]]
```
where N is the max number of tokens that you want to be generated and inserted into the text file by the LLM. N must be a positive integer greater than zero. Hit Ctrl+Enter to generate and the FIM tag will be deleted. Then text from the LLM will be streamed into the text file at the location where the [[[N]]] tag was before it was deleted.

When you hit Ctrl+Enter to generate in FIMpad, the cursor needs to be inside of or right next to the tag that you want to generate for. The asterisks below indicate a few examples of acceptable locations for the cursor when you hit Ctrl+Enter to generate a [[[N]]] tag.
```
*[[[100]]]
[*[[100]]]
[[[10*0]]]
[[[100]]]*
```

For FIM generation, everything in the text file before the FIM tag is sent to the LLM as prefix text, and everything in the text file after the FIM tag is sent to the LLM as suffix text. The LLM uses both prefix text and suffix text as context, and it sends back text that it deems likely to appear between them. However, sometimes you won't want all the text in the text file to be sent as either prefix or suffix text. This is where the [[[prefix]]] and [[[suffix]]] tags come in.

### Prefix and Suffix Tags (only work for FIM generation)

In order to control which text is sent to the LLM as context for FIM generation, you can use the [[[prefix]]] and [[[suffix]]] tags. These tags are optional companions to [[[N]]] tags. Wherever the [[[prefix]]] tag is placed in the document, that marks the start of the prefix. Wherever the [[[suffix]] tag is placed in the document, that marks the end of the suffix.

When you are using [[[N]]] with [[[prefix]]] and/or [[[suffix]]] , upon hitting Ctrl+Enter to generate, all three tags will be deleted. Then text from the LLM will be streamed into the text file at the location where the [[[N]]] tag was before it was deleted.

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

The line with "Joe: Yes" is where it ran out of tokens before it could add more words or punctuation. We'll see how to deal with that in the next section.

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

This time Joe has a favorable opinion of poodles. With the variability of LLM output, it is not guaranteed that he would. But it is far more likely when we hide the part of the prefix that says that he strongly dislikes all types dogs.

Hiding prefix is not just about what facts the model knows in context, it is also about formatting and patterns. I used the examples above because they were short. But in a longer example with things like stage directions or narration, you would hide those when you want the model to generate only dialogue.

Note that the 20 tokens were used up by the time that Joe said "quite", mid-line again. We need a way to get the model to stop at clean point in the text.

## Stop Sequences













