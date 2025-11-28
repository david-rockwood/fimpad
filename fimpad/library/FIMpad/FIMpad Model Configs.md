# FIMpad Model Configs

Place the caret within a config tag below and press Alt+= (or use the menu entry at `AI -> Apply Config Tag`) to apply them to your FIMpad configuration settings.

---

## IBM Granite 4.0 H (any parameter size, base or instruct)

These are the default FIM token settings for FIMpad.

```
[[[{
"fim_prefix": "<|fim_prefix|>",
"fim_suffix": "<|fim_suffix|>",
"fim_middle": "<|fim_middle|>",
}]]]
```

---

## Mistral Small 3.1 (base or instruct)

```
[[[{
"fim_prefix": "[PREFIX]",
"fim_suffix": "[SUFFIX",
"fim_middle": "[MIDDLE]",
}]]]
```

---

## Completion-only mode for any LLM

If you are going to use a model without FIM control tokens, apply the config tag below to make FIMpad run in completion-only mode. This way FIMpad will not send the LLM FIM tokens that the LLM will misinterpret. This setting may also be useful for system/user/assistant chats with instruct models that do have FIM control tokens, because you want to run system/user/assistant chats as completions, not FIM.

```
[[[{
"fim_prefix": "",
"fim_suffix": "",
"fim_middle": "",
}]]]
```
