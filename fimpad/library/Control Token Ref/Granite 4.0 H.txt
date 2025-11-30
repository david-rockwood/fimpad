# Granite 4.0 H control token reference

---

## Control tokens
```
{
  "version": "1.0",
  "truncation": null,
  "padding": null,
  "added_tokens": [
    {
      "id": 100256,
      "content": "<|pad|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100257,
      "content": "<|end_of_text|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100258,
      "content": "<|fim_prefix|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 100259,
      "content": "<|fim_middle|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 100260,
      "content": "<|fim_suffix|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 100261,
      "content": "<|fim_pad|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 100262,
      "content": "<|filename|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 100263,
      "content": "<|reponame|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 100264,
      "content": "<|start_of_role|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100265,
      "content": "<|end_of_role|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100266,
      "content": "<|unused_1|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100267,
      "content": "<|start_of_plugin|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100268,
      "content": "<|end_of_plugin|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100269,
      "content": "<|unk|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100270,
      "content": "<tool_call>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 100271,
      "content": "</tool_call>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 100272,
      "content": "<tool_response>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 100273,
      "content": "</tool_response>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 100274,
      "content": "<think>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 100275,
      "content": "</think>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 100276,
      "content": "<think_on>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100277,
      "content": "<think_off>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100278,
      "content": "<schema>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100279,
      "content": "</schema>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100280,
      "content": "<tools>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100281,
      "content": "</tools>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100282,
      "content": "<documents>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 100283,
      "content": "</documents>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    }
}
```

---

## Additional notes

### Overview
Granite 4.0 introduces a hybrid Mamba-2/transformer architecture, with a Mixture-of-Experts (MoE) strategy in select models, delivering more than 70% lower memory requirements and 2x faster inference speeds compared to similar models, particularly in multi-session and long-context scenarios. The models deliver strong performance across benchmarks, with Granite 4.0 Small achieving industry-leading results in key agentic tasks like instruction following and function calling. These efficiencies make the models well-suited for a wide range of use cases like retrieval-augmented generation (RAG), multi-agent workflows, and edge deployments. Granite 4.0 is released under Apache 2.0, cryptographically signed for authenticity, and the first open model family certified under ISO 42001.

### Models
Model	Architecture Type	Model Size	Intended Use
Granite-4.0-H-Small Granite H Small	Hybrid, Mixture of Experts	32B total / 9B activated	Workhorse model for key enterprise tasks like RAG and agents
Granite-4.0-H-Tiny Granite H Tiny	Hybrid, Mixture of Experts	7B total / 1B activated	Designed for low latency and local applications, particularly where the task has long prefill or other scenarios where a MoE model is desired
Granite-4.0-H-Micro Granite H Micro	Hybrid, Dense	3B total	Designed for low latency and local applications, and as a building block to perform key tasks (like function calling) quickly within agentic workflows
Granite-4.0-Micro Granite Micro	Traditional, Dense	3B total	Alternative option for users when Mamba2 support is not yet optimized (e.g. llama.cpp, PEFT, etc)
Granite-4.0-H-1B Granite H 1B	Dense, Hybrid	1.5B	Ideal models for edge, on-device, and latency-sensitive use cases
Granite-4.0-1B Granite 1B Hybrid	Dense, Traditional	1B	Alternative option for users when Mamba2 support is not yet optimized (e.g. llama.cpp, PEFT, etc)
Granite-4.0-H-350M Granite H 350M	Dense, Hybrid	350M	Similar use cases as Granite-4.0-H-1B, but even smaller and cheaper to run
Granite-4.0-350M Granite 350M Hybrid	Dense, Traditional	350M	Alternative option for users when Mamba2 support is not yet optimized (e.g. llama.cpp, PEFT, etc)
​
### Inference Examples​
```
<|start_of_role|>user<|end_of_role|>What is the largest ocean on Earth?<|end_of_text|>
<|start_of_role|>assistant<|end_of_role|>The largest ocean on Earth is the Pacific Ocean. It covers an area of about 63.8 million square miles (165.25 million square kilometers), which is more than twice the size of the second-largest ocean, the Atlantic Ocean. The Pacific Ocean lies between the Americas to the east and Asia and Australia to the west.<|end_of_text|>
```

The Granite 4 models work best with temperature set to 0 for most inferencing tasks.
​
### Tools
```
<|start_of_role|>system<|end_of_role|>You are a helpful assistant with access to the following tools. You may call one or more tools to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{"type": "function", "function": {"name": "get_current_weather", "description": "Get the current weather", "parameters": {"type": "object", "properties": {"location": {"description": "The city and state, e.g. San Francisco, CA", "type": "string"}}, "required": ["location"]}}}
{"type": "function", "function": {"name": "get_stock_price", "description": "Retrieves the current stock price for a given ticker symbol. The ticker symbol must be a valid symbol for a publicly traded company on a major US stock exchange like NYSE or NASDAQ. The tool will return the latest trade price in USD. It should be used when the user asks about the current or most recent price of a specific stock. It will not provide any other information about the stock or company.", "parameters": {"type": "object", "properties": {"ticker": {"description": "The stock ticker symbol, e.g. AAPL for Apple Inc.", "type": "string"}}}}}
</tools>

For each tool call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call>. If a tool does not exist in the provided list of tools, notify the user that you do not have the ability to fulfill the request.<|end_of_text|>
<|start_of_role|>user<|end_of_role|>What's the current weather in New York?<|end_of_text|>
<|start_of_role|>assistant<|end_of_role|><tool_call>
{"name": "get_current_weather", "arguments": {"city": "New York"}}
</tool_call><|end_of_text|>
<|start_of_role|>user<|end_of_role|>
<tool_response>
New York is sunny with a temperature of 30°C.
</tool_response><|end_of_text|>
<|start_of_role|>user<|end_of_role|>OK, Now tell me what's the weather like in Bengaluru at this moment?<|end_of_text|>
<|start_of_role|>assistant<|end_of_role|><tool_call>
{"name": "get_current_weather", "arguments": {"city": "Bengaluru"}}
</tool_call><|end_of_text|>
```

Consider the following points to build promts for tool-calling tasks:
- When a list of tools is supplied, the chat template automatically formats this list as a system prompt. See the Chat Template Design section for more information about system prompt design in tool-calling scenarios.
- Please follow OpenAI’s function definition schema to define tools.
- Granite 4.0 chat template automatically returns tool calls between <tool_call> and </tool_call> tags within the assistant turn. Refer to the Chat Template Design section for examples.
- The Granite 4.0 chat template converts content from tool role into a user role, where tool responses appear between <tool_response> and </tool_response> tags. This conversion occurs automatically when using libraries that apply the chat template for you. However, users who build prompts directly in Jinja must ensure that tool responses are formatted according to the Granite 4.0 chat template. Please, refer to the Chat Template Design section for examples.

### RAG:
```
<|start_of_role|>system<|end_of_role|>You are a helpful assistant with access to the following documents. You may use one or more documents to assist with the user query.

You are given a list of documents within <documents></documents> XML tags:
<documents>
{"doc_id": 1, "title": "Bridget Jones: The Edge of Reason (2004)", "text": "Bridget Jones: The Edge of Reason (2004) - Bridget is currently living a happy life with her lawyer boyfriend Mark Darcy, however not only does she start to become threatened and jealous of Mark's new young intern, she is angered by the fact Mark is a Conservative voter. With so many issues already at hand, things get worse for Bridget as her ex-lover, Daniel Cleaver, re-enters her life; the only help she has are her friends and her reliable diary.", "source": ""}
{"doc_id": 2, "title": "Bridget Jones's Baby (2016)", "text": "Bridget Jones's Baby (2016) - Bridget Jones is struggling with her current state of life, including her break up with her love Mark Darcy. As she pushes forward and works hard to find fulfilment in her life seems to do wonders until she meets a dashing and handsome American named Jack Quant. Things from then on go great, until she discovers that she is pregnant but the biggest twist of all, she does not know if Mark or Jack is the father of her child.", "source": ""}
{"doc_id": 3, "title": "Bridget Jones's Diary (2001)", "text": "Bridget Jones's Diary (2001) - Bridget Jones is a binge drinking and chain smoking thirty-something British woman trying to keep her love life in order while also dealing with her job as a publisher. When she attends a Christmas party with her parents, they try to set her up with their neighbours' son, Mark. After being snubbed by Mark, she starts to fall for her boss Daniel, a handsome man who begins to send her suggestive e-mails that leads to a dinner date. Daniel reveals that he and Mark attended college together, in that time Mark had an affair with his fiancée. Bridget decides to get a new job as a TV presenter after finding Daniel being frisky with a colleague. At a dinner party, she runs into Mark who expresses his affection for her, Daniel claims he wants Bridget back, the two fight over her and Bridget must make a decision who she wants to be with.", "source": ""}
</documents>

Write the response to the user's input by strictly aligning with the facts in the provided documents. If the information needed to answer the question is not available in the documents, inform the user that the question cannot be answered based on the available data.<|end_of_text|>
<|start_of_role|>user<|end_of_role|>Could you please tell me what the first Bridget Jones's movie is about?, please be brief in your response.<|end_of_text|>
<|start_of_role|>assistant<|end_of_role|>The first Bridget Jones's movie, "Bridget Jones's Diary" (2001), is about a thirty-something British woman named Bridget Jones who is trying to keep her love life in order while also dealing with her job as a publisher. She attends a Christmas party with her parents, where they try to set her up with their neighbours' son, Mark. After being snubbed by Mark, she starts to fall for her boss Daniel, a handsome man who begins to send her suggestive emails. Bridget decides to get a new job as a TV presenter after finding Daniel being frisky with a colleague. At a dinner party, she runs into Mark who expresses his affection for her, Daniel claims he wants Bridget back, the two fight over her and Bridget must make a decision who she wants to be with.<|end_of_text|>
```

Consider the following points to build promts for RAG tasks:

- The chat template lists documents as part of the system turn between <documents> and </documents> tags. Please, refert to Chat Template Design section for further details.
- Documents are provided to the model as a list of dictionaries, with each dictionary representing a document. We recommend formatting documents as follows:
```
{
"doc_id": 1,
"title": "History Document Title",
"text": "From the early 12th century, French builders developed the Gothic style, marked by the use of rib vaults, pointed arches, flying buttresses, and large stained glass windows. It was used mainly in churches and cathedrals, and continued in use until the 16th century in much of Europe. Classic examples of Gothic architecture include Chartres Cathedral and Reims Cathedral in France as well as Salisbury Cathedral in England. Stained glass became a crucial element in the design of churches, which continued to use extensive wall-paintings, now almost all lost.",
"source": ""
}
```

### FIM
```
<|start_of_role|>user<|end_of_role|><|fim_prefix|>
def fibonacci(n):
result =
<|fim_suffix|>
return result
<|fim_middle|><|end_of_text|>
<|start_of_role|>assistant<|end_of_role|>    if n == 0:
    return 0
elif n == 1:
    return 1
else:
    return fibonacci(n-1) + fibonacci(n-2)
<|end_of_text|>
```

Consider the following points to build prompts for FIM coding tasks:

- The tags supported for fill-in-the-middle (FIM) code completion are: <|fim_prefix|>, <|fim_middle|>, and <|fim_suffix|>. Make sure to use the correct FIM tags when using Granite 4.0 models for FIM code completions.
- Prepend code before the missing part with the tag <|fim_prefix|>
- Prepend code after the missing part with the tag <|fim_suffix|>
- End your prompt with the tag <|fim_middle|> to indicate to the model something is missing in the code snippet.
- Completion of basic programming concepts (e.g., function, method, conditionals, loops) is covered for various programming languages (e.g., python, c/c++, go, java).

​### JSON
```
<|start_of_role|>system<|end_of_role|>You are a helpful assistant that answers in JSON. Here's the json schema you must adhere to:
<schema>
{"title": "LeisureActivityBooking", "type": "object", "properties": {"activityID": {"title": "Activity ID", "type": "string"}, "participantInfo": {"title": "Participant Info", "type": "object", "properties": {"participantName": {"title": "Participant Name", "type": "string"}, "age": {"title": "Age", "type": "integer"}}, "required": ["participantName", "age"]}, "activityDate": {"title": "Activity Date", "type": "string", "format": "date"}, "equipmentNeeded": {"title": "Equipment Needed", "type": "array", "items": {"type": "string"}}}, "required": ["activityID", "participantInfo", "activityDate"]}
</schema>
<|end_of_text|>
<|start_of_role|>user<|end_of_role|>I'm planning a kayaking trip for my friend's birthday on April 15th, and I need to book it through your leisure activity service. The activity will be for my friend, Jamie Patterson, who is 27 years old. We'll need two kayaks, paddles, and safety vests. The activity ID for this booking is 'KAYAK-0423'. The date we're looking to book the kayaking activity is specifically on the 15th of April, 2023. To summarize, the equipment needed for this adventure includes two kayaks, a pair of paddles, and two safety vests to ensure a safe and enjoyable experience on the water.<|end_of_text|>
<|start_of_role|>assistant<|end_of_role|>{"activityID": "KAYAK-0423", "participantInfo": {"participantName": "Jamie Patterson", "age": 27}, "activityDate": "2023-04-15", "equipmentNeeded": ["kayak", "paddle", "safety vest"]}<|end_of_text|>
```
