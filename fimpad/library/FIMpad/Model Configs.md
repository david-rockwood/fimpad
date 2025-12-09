# FIMpad Model Configs

Place the caret within a config tag below and press Alt+C (or use the menu entry at `AI -> Apply Config Tag`) to apply the settings to your FIMpad configuration.

---

## Default FIM control Tokens

These are known to work for Qwen 3 and IBM Granite 4.0 H LLMs.

```
[[[{
"fim_prefix": "<|fim_prefix|>",
"fim_suffix": "<|fim_suffix|>",
"fim_middle": "<|fim_middle|>",
}]]]
```

---

## GLM 4.6 V

These have been tested with GLM 4.6 V Flash, So far, in brief testing, Flash does not seem to complete within the given max token limit as often as other FIM-capable models do, but the fills are relevant to the prefix and suffix.

```
[[[{
"fim_prefix": "<|code_prefix|>",
"fim_suffix": "<|code_suffix|>",
"fim_middle": "<|code_middle|>",
}]]]
```

---

## Completion-only mode for any LLM

If you want to use a model without FIM control tokens, apply the config tag below to make FIMpad run in completion-only mode. This way FIMpad will not send the LLM any FIM tokens that the LLM would misinterpret, and it will not send suffix text. This setting may also be useful for system/user/assistant chats with instruct models that do have FIM control tokens, because you want to run system/user/assistant chats as completions, not FIM.

```
[[[{
"fim_prefix": "",
"fim_suffix": "",
"fim_middle": "",
}]]]
```
