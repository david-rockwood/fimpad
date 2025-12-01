# Qwen 3 Next and Coder control token reference

---

## Control tokens
```
{
  "version": "1.0",
  "truncation": null,
  "padding": null,
  "added_tokens": [
    {
      "id": 151643,
      "content": "<|endoftext|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 151644,
      "content": "<|im_start|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 151645,
      "content": "<|im_end|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 151646,
      "content": "<|object_ref_start|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 151647,
      "content": "<|object_ref_end|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 151648,
      "content": "<|box_start|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 151649,
      "content": "<|box_end|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 151650,
      "content": "<|quad_start|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 151651,
      "content": "<|quad_end|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 151652,
      "content": "<|vision_start|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 151653,
      "content": "<|vision_end|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 151654,
      "content": "<|vision_pad|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 151655,
      "content": "<|image_pad|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 151656,
      "content": "<|video_pad|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": true
    },
    {
      "id": 151657,
      "content": "<tool_call>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 151658,
      "content": "</tool_call>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 151659,
      "content": "<|fim_prefix|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 151660,
      "content": "<|fim_middle|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 151661,
      "content": "<|fim_suffix|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 151662,
      "content": "<|fim_pad|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 151663,
      "content": "<|repo_name|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 151664,
      "content": "<|file_sep|>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 151665,
      "content": "<tool_response>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 151666,
      "content": "</tool_response>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 151667,
      "content": "<think>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    },
    {
      "id": 151668,
      "content": "</think>",
      "single_word": false,
      "lstrip": false,
      "rstrip": false,
      "normalized": false,
      "special": false
    }
}
```

---

## Additional notes
```
<|im_start|>system
{system_prompt}<|im_end|>
<|im_start|>user
{prompt}<|im_end|>
<|im_start|>assistant
```

### Qwen3-Next-80B-A3B-Instruct has the following features:

Type: Causal Language Models
Training Stage: Pretraining (15T tokens) & Post-training
Number of Parameters: 80B in total and 3B activated
Number of Paramaters (Non-Embedding): 79B
Hidden Dimension: 2048
Number of Layers: 48
- Hybrid Layout: 12 * (3 * (Gated DeltaNet -> MoE) -> 1 * (Gated Attention -> MoE))
Gated Attention:
- Number of Attention Heads: 16 for Q and 2 for KV
- Head Dimension: 256
- Rotary Position Embedding Dimension: 64
Gated DeltaNet:
- Number of Linear Attention Heads: 32 for V and 16 for QK
- Head Dimension: 128
Mixture of Experts:
- Number of Experts: 512
- Number of Activated Experts: 10
- Number of Shared Experts: 1
- Expert Intermediate Dimension: 512
Context Length: 262,144 natively and extensible up to 1,010,000 tokens

### To achieve optimal performance, Qwen recommends the following settings:

We suggest using temperature=0.7, top_p=0.8, top_k=20, and min_p=0.0 presence_penalty between 0 and 2 if the framework supports to reduce endless repetitions.

temperature = 0.7

top_k = 20

min_p = 0.00 (llama.cpp's default is 0.1)

top_p = 0.80

presence_penalty = 0.0 to 2.0 (llama.cpp default turns it off, but to reduce repetitions, you can use this) Try 1.0 for example.

Supports up to 262,144 context natively but you can set it to 32,768 tokens for less RAM use

### Llama.cpp: Run Qwen3-Next-80B-A3B-Instruct Tutorial

Obtain the latest llama.cpp on GitHub here. You can follow the build instructions below as well. Change -DGGML_CUDA=ON to -DGGML_CUDA=OFF if you don't have a GPU or just want CPU inference.

apt-get update
apt-get install pciutils build-essential cmake curl libcurl4-openssl-dev -y
git clone https://github.com/ggml-org/llama.cpp
cmake llama.cpp -B llama.cpp/build \
-DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=ON -DLLAMA_CURL=ON
cmake --build llama.cpp/build --config Release -j --clean-first --target llama-cli llama-gguf-split
cp llama.cpp/build/bin/llama-* llama.cpp

You can directly pull from HuggingFace via:

./llama.cpp/llama-cli \
-hf unsloth/Qwen3-Next-80B-A3B-Instruct-GGUF:Q4_K_XL \
--jinja -ngl 99 --threads -1 --ctx-size 32684 \
--temp 0.7 --min-p 0.0 --top-p 0.80 --top-k 20 --presence-penalty 1.0
