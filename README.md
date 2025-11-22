# FIMpad

A text editor that can do fill-in-the-middle LLM text generation within a text file.

The first release will likely be in December 2025.

If you don't mind bugs you can try it early by following the quick start below, or by getting the latest CI artifact build for Linux in the actions tab.

## Quick start

```bash
git clone https://github.com/david-rockwood/fimpad
cd fimpad
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m fimpad
```

## Overview

FIMpad is an AI sandbox and a text editor. The text editor is the interface to the LLM. AI workflows live in regular text files, and sessions can be saved to and resumed from a text file. You can do fill-in-the-middle (FIM) generation at any point in a text file. FIM generation is a versatile, powerful, and quick way to help with story writing and coding, among many other things.

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

> Four score and seven **[[[50]]]**


The number 50 is enclosed in triple brackets. This FIM tag will stream a maximum of 50 tokens into the document. The tag will be deleted before streaming insertion. To execute a FIM tag, click inside the FIM tag such that the carat is within or directly adjacent to the FIM tag. Then press Ctrl+Enter (or use the menu entry at AI->Generate.) Below is an example of the result (although your result may not be an exact match due to the variability of LLM generation.).

> Four score and seven years ago, our fathers brought forth on this continent, a new nation, conceived in Liberty, and dedicated to the proposition that all men are created equal. Now we are engaged in a great civil war, testing whether that nation, or any nation so


Upon execution of the FIM tag, the tag is deleted from the document. All of the text between the beginning of the file and the location of the now-deleted FIM tag is considered **prefix text**. All of the text between the now-deleted FIM tag and the end of the file is considered **suffix text**. The prefix and the suffix are sent to the LLM server, and then the LLM server streams back the 50 (or fewer) tokens that the LLM deems most likely to appear between the prefix and the suffix.

In the above example, the document was empty past the FIM tag, so the LLM received an empty string for the suffix. In cases like this the streamed response is essentially a completion of the prefix.

Any valid tag that has an integer as the fourth character after the three opening bracket characters is a FIM tag.

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
> Jane: **[[[75]]]**

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

The LLM generated multiple comments for John and Jane. In a situation where you want to chat, as John, with Jane, you want the generation to stop after Jane's comment, not John's, so that you can respond as John. And you want only one comment from Jane. And ideally the text inserted from the LLM will end exactly after "John: ", so that you can just start typing your response. You can set this up with the stop() function. The argument given to stop() is a **stop sequence**, which is a sequence of characters that tell FIMpad where to cut off the generation. If the stop sequence is generated by the LLM, the stop sequence characters are the last characters that will be inserted into the document for that FIM tag generation. See the example below, before generation.

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
> Jane: **[[[75;stop("John: ")]]]**

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
> Jane: **[[[75;stop("John: ");append("\nJane: ")]]]**

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

## Writing a story with FIMpad

One strategy for writing a story with FIMpad is to start with a sentence that you don't know how to finish.

> It was a dark and stormy midnight at the zoo, and the scene in the night shift employee break room near the gorilla enclosure was as boring as ever; however, **[[[120]]]**

after generation:

> It was a dark and stormy midnight at the zoo, and the scene in the night shift employee break room near the gorilla enclosure was as boring as ever; however, 5 minutes later, all the employees would be having a near heart-attack and all the zoo animals would be wondering what the hell just happened.
>
>The zoo had recently acquired a new gorilla, named George, who had quickly become a favorite among visitors and staff alike. George was a massive silverback gorilla with a personality that was as large as his body. He was known for his playful antics, his love of bananas, and his uncanny ability to mimic human behavior.
>
>One night, a new night shift employee named Jake was on duty. Jake was a young man in his early twenties,

I don't want George to be known for his playful antics, so I estimate the description for something else that he could be known for at about 5 tokens, and I do this:

> It was a dark and stormy midnight at the zoo, and the scene in the night shift employee break room near the gorilla enclosure was as boring as ever; however, 5 minutes later, all the employees would be having a near heart-attack and all the zoo animals would be wondering what the hell just happened.
>
> The zoo had recently acquired a new gorilla, named George, who had quickly become a favorite among visitors and staff alike. George was a massive silverback gorilla with a personality that was as large as his body. He was known for his **[[[5]]]** , his love of bananas, and his uncanny ability to mimic human behavior.
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
> One night, a new night shift employee named Jake was on duty. Jake was a young man in his early twenties, **[[[120]]]**
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
> Jake's heart started to race as he stood up and walked towards the enclosure. As he got closer, **[[[55;stop(".\n","?\n","!\n")]]]**

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

I must end the exploration of writing fiction with FIMpad here or this README will become too long, but the above examples demonstrate three fundamental ways to use FIM generation for stories: completion, replacement, and interpolation. These ways of using FIM generation can diminish or even eliminate writer's block.

## Virtual chat roles

Many who are familiar with LLMs are used to role-based chat, where the standard roles are: **system**, **user**, and **assistant**. The system prompt sets the overall rules for, and the personality of, the LLM assistant. The user prompts are messages that the human user sends to the LLM. The assistant responses are messages that the LLM sends back to the user.

Early versions of FIMpad had [[[system]]], [[[user]]], and [[[assistant]]] tags, with complementary closing tags for each, to enable standard role-based chat. But these tags made FIMpad unwieldy, overly complicated. And it turns out that you can simulate this well with FIM generation, likely due to LLM training data including transcripts of role-based chats.

Below is an example of how to start a virtual role-based chat, before generation.

> ^^^^^SYSTEM PROMPT^^^^^
>
> You are a helpful assistant.
>
>
> ^^^^^USER PROMPT^^^^^
>
> what's up MAN!
>
>
> ^^^^^ASSISTANT RESPONSE^^^^^
>
> Hello! How can I help you today?
>
>
> ^^^^^USER PROMPT^^^^^
>
> oh im gonna travel to BRAZIL! what city should I go to in brazill where thier will be a lott of beatiful women?  i wanna meet them
>
>
> ^^^^^ASSISTANT RESPONSE^^^^^
>
> **[[[1000;append("\n\n\n^^^^^USER PROMPT^^^^^\n")]]]**

after generating two turns:

> ^^^^^SYSTEM PROMPT^^^^^
>
> You are a helpful assistant.
>
>
> ^^^^^USER PROMPT^^^^^
>
> what's up MAN!
>
>
> ^^^^^ASSISTANT RESPONSE^^^^^
>
> Hello! How can I help you today?
>
>
> ^^^^^USER PROMPT^^^^^
>
> oh im gonna travel to BRAZIL! what city should I go to in brazill where thier will be a lott of beatiful women?  i wanna meet them
>
>
> ^^^^^ASSISTANT RESPONSE^^^^^
>
> Brazil is a beautiful country with many vibrant cities. Some popular destinations that are known for their beauty include Rio de Janeiro, São Paulo, Salvador, and Florianópolis. Each city has its own unique culture, attractions, and nightlife. I would recommend doing some research to find a city that aligns with your interests and preferences.
>
>
> ^^^^USER PROMPT^^^^^
>
> tell me more about rio
>
>
> ^^^^^ASSISTANT RESPONSE^^^^^
>
> Rio de Janeiro, often simply called Rio, is the second-largest city in Brazil and one of the most iconic. It is known for its stunning beaches like Copacabana and Ipanema, the famous statue of Christ the Redeemer atop Corcovado mountain, the lively Carnival festival, and the vibrant Samba culture. 
>
> Rio has a diverse population and is famous for its beauty. Some popular places to visit include:
>
> - The beaches of Copacabana, Ipanema, and Leblon
>
> - Christ the Redeemer statue and Corcovado mountain
>
> - Sugarloaf Mountain
>
> - The historic neighborhood of Santa Teresa
>
> - Maracanã Stadium, home of the 2014 World Cup and 2016 Olympics
>
> - Lively nightlife in Lapa and other neighborhoods
>
> Rio is a popular tourist destination with something to offer everyone, from stunning natural beauty to rich culture and history. Just be aware that like any major city, there are safety concerns to be aware of. Research the areas you plan to visit and use common sense precautions.
>
>I hope this gives you a good overview of what Rio de Janeiro has to offer! Let me know if you have any other questions.
>
>
> ^^^^^USER PROMPT^^^^^

Note that the first assistant response is shorter than the second assistant response, even though both FIM tags specified a max of 1000 tokens. This is apparently because a shorter response seemed appropriate to the LLM for the first user prompt, so it didn't use the full amount of tokens available. In fact, the second response looks far shorter than 1000 tokens as well. You don't always get the max from the LLM. If you wanted the assistant to give longer responses, you could probably achieve that by writing a longer example response for the assistant in the prefix. And if you didn't feel like writing that long example assistant response, you could generate it by completions with FIM tags. Every time the LLM stopped early, you would type the first few words of a new sentence and then generate again.

## Slicing up context

At first glance it seems like FIM generation lacks memory in comparison to standard role-based (system/user/assistant) chats with LLMs. After all, role-based chats have a chat history, a list of messages that all make up the context for the duration of a chat session. But FIM generation does have memory; it lives in the prefix and in the suffix. And in FIMpad, the prefix and the suffix are on full display in the document. And they are editable.
























