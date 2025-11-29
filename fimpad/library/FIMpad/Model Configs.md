# FIMpad Model Configs

Place the caret within a config tag below and press Alt+= (or use the menu entry at `AI -> Apply Config Tag`) to apply the settings to your FIMpad configuration.

---

## IBM Granite 4.0 H Base (any parameter size)

These are the default FIM control token settings for FIMpad.

```
[[[{
"fim_prefix": "<|fim_prefix|>",
"fim_suffix": "<|fim_suffix|>",
"fim_middle": "<|fim_middle|>",
}]]]
```

---

## Mistral Small 3.1 Base

```
[[[{
"fim_prefix": "[PREFIX]",
"fim_suffix": "[SUFFIX]",
"fim_middle": "[MIDDLE]",
}]]]
```

---

## Completion-only mode for any LLM

If you want to use a model without FIM control tokens, apply the config tag below to make FIMpad run in completion-only mode. This way FIMpad will not send the LLM any FIM tokens that the LLM would misinterpret. This setting may also be useful for system/user/assistant chats with instruct models that do have FIM control tokens, because you want to run system/user/assistant chats as completions, not FIM.

```
[[[{
"fim_prefix": "",
"fim_suffix": "",
"fim_middle": "",
}]]]
```
