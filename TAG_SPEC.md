# FIMpad Tag Specification

## 0. Tag Types

All FIMpad tags start with `[[[` and end with `]]]`. The first character **after** `[[[` determines the kind of tag:

* **Digit** (`0–9`) → **FIM tag** (generation tag)
* **Double quote** (`"`) → **Sequence tag**
* **Left parenthesis** (`(`) → **Comment tag**
* **Letter** starting a recognized word → **Prefix/Suffix tag**
  (`prefix`, `PREFIX`, `suffix`, `SUFFIX`)

Any other pattern is treated as plain text or a syntax error.

---

## 1. Lexical Conventions

* `WS` = whitespace (space, tab, newline, etc.)
* Identifiers:
  `IDENT ::= [A-Za-z_][A-Za-z0-9_]*`
* Numbers (for `N` and numeric args):
  `INT ::= [0-9]+`
* String literals (used inside functions and sequence tags):

  ```ebnf
  STRING ::= '"' { CHAR } '"'
  CHAR   ::= any character except '"' or '\'
           | '\' ESC
  ESC    ::= '"' | '\' | 'n' | 't'
  ```

  with standard interpretation inside the STRING:

  * `\"` → `"`
  * `\\` → `\`
  * `\n` → newline
  * `\t` → tab

  Outside of string literals, `\n` is just two characters (`\` and `n`).

---

## 2. FIM Tags (Generation Tags)

### 2.1 Syntax

A FIM tag is a “mini program” enclosed in `[[[` and `]]]`, and **must** begin with an integer `N` (the max tokens):

```ebnf
FIMTag ::= '[[' '[' '[' WS? FIMBody WS? ']' ']' ']'

FIMBody ::= FIMStmt (';' WS? FIMStmt)* ';'?
FIMStmt ::= INT | FuncCall

FuncCall ::= IDENT WS? '(' WS? ArgList? WS? ')'
ArgList  ::= Arg (WS? ',' WS? Arg)*

Arg      ::= STRING | INT | IDENT
```

* `INT` as a statement is always the first statement and is interpreted as `N`, the max tokens to generate.
* All other statements are function calls, e.g.:

  ```text
  [[[100;stop("User: ");chop("END");append_nl(2);append("Done.\n")]]]
  ```

A FIM tag can be formatted across multiple lines for readability:

```text
[[[
  100;
  name("step1");
  stop("User: ");
  chop("END_OF_SECTION");
  append_nl(2);
  append("That is my final answer.\n");
]]]
```

Whitespace and newlines are ignored between tokens.

### 2.2 Functions and Phases

Each function belongs to **one** of two conceptual phases:

* **Init-time (before streaming / request configuration)**
  Evaluated in order before calling the model.

  * `name("id")`
  * `stop(pattern1, pattern2, ...)`
  * `chop(pattern1, pattern2, ...)`
  * `temp(float)`
  * `top_p(float)`

  Use `temp("0.5")` or `top_p("0.8")` to override the corresponding
  sampling settings for a single FIM tag.

* **Post-time (after streaming completes)**
  Evaluated in order on the final generated text.

  * `append(string)`
  * `append_nl(int)`  (append `int` newline characters, default 1 if omitted)

#### Execution Order

For one FIM tag:

1. **Parse** the body into:

   * `N` (max tokens)
   * ordered list of functions `f₁, f₂, ..., fₖ`
2. **Init phase**:
   Scan `f₁..fₖ` in order and execute all init-time functions (config and stop rules).
3. **LLM call**:
   Call the model with the resulting config and precomputed context. During streaming, the underlying implementation respects the registered `stop`/`chop` rules (see 2.3), but this is not exposed as a separate phase to the DSL.
4. **Post phase**:
   Once streaming is done, take the final text and apply all post-time functions in order.

### 2.3 `stop()` and `chop()` Semantics

Both take **one or more** string arguments:

```text
stop("User: ", "Assistant: ")
chop("STEP_2", "END_OF_SECTION")
```

Conceptually, they register stop rules:

* `stop(pattern)` → stop when `pattern` appears, **keep** the pattern in the document.
* `chop(pattern)` → stop when `pattern` appears, **remove** the pattern from the document.

For multiple patterns and multiple calls:

* Each `(pattern, include_or_exclude)` pair is collected with an internal priority derived from its position in the tag (left-to-right, top-to-bottom).
* During streaming, the implementation:

  * Tracks all patterns in the accumulated output.
  * On the *first* match (minimum character offset), stops generation.
  * If multiple patterns match at the same offset, the one whose function occurred earlier in the FIM tag wins.

Newlines in patterns:

* `stop("User:\n")` → stops when actual newline follows `User:`.
* `stop("User:\\n")` → stops on literal `User:\n` (backslash + `n`).

### 2.4 `name("id")` and Named FIM Tags

`name("id")` is an init-time function that gives a FIM tag a **unique identifier** within a document:

```text
[[[
  100;
  name("expand_intro");
  stop("SECTION 2\n");
]]]
```

* On parsing the document, FIMpad builds a registry:

  ```text
  id → FIMTag
  ```

* If two or more FIM tags use the same `id`, this is an error:

  * Those tags are considered invalid for execution.
  * Any sequence tag referring to that `id` will also error.

---

## 3. Sequence Tags

Sequence tags orchestrate multiple **named FIM tags**. They do not call the model themselves.

### 3.1 Syntax

A sequence tag is a list of string literals inside `[[[` `]]]` that **does not** start with a digit:

```ebnf
SequenceTag ::= '[[' '[' '[' WS? SeqBody WS? ']' ']' ']'

SeqBody ::= STRING (';' WS? STRING)* ';'?
```

Example:

```text
[[[
  "step1";
  "step2";
  "step3";
]]]
```

Rules:

* No `N` number at the beginning.
* No functions; only string literals separated by semicolons.
* Sequence tags **cannot** be named (no `name()`).

### 3.2 Semantics

On executing a sequence tag:

1. Build or refresh the `id → FIMTag` registry using all `name("id")` calls in the document.
2. For each `"id"` in the sequence, in order:

   * If `id` is not found in the registry → **error** (e.g. “Unknown FIM tag 'step2' in sequence”) and **abort the entire sequence**.
   * If `id` is found → execute that FIM tag as if the user had executed it directly.

Restrictions:

* Sequence tags may reference **only** named FIM tags.
* Sequence tags do **not** reference other sequence tags (no nesting/recursion in v1).

Each FIM tag runs against the current document content, so earlier steps can mutate the text for later steps.

---

## 4. Prefix / Suffix Tags

Prefix/suffix tags define context windows for FIM tags. There are **soft** (lowercase) and **hard** (uppercase) variants.

### 4.1 Syntax

```ebnf
PrefixTag ::= '[[[' ('prefix' | 'PREFIX') ']' ']' ']'
SuffixTag ::= '[[[' ('suffix' | 'SUFFIX') ']' ']' ']'
```

Accepted forms:

* Soft prefix: `[[[prefix]]]`
* Hard prefix: `[[[PREFIX]]]`
* Soft suffix: `[[[suffix]]]`
* Hard suffix: `[[[SUFFIX]]]`

### 4.2 Soft vs Hard Semantics

* **Soft** tags (`prefix`, `suffix`):

  * May be *auto-deleted* after generation when they are used.
* **Hard** tags (`PREFIX`, `SUFFIX`):

  * Are **never** auto-deleted.

### 4.3 How FIM Tags Use Prefix/Suffix

For a given FIM tag at position `P` in the document:

1. **Left boundary (prefix)**:

   * Scan backward from `P` for the nearest `PrefixTag` (soft or hard).
   * If found, the prefix boundary is immediately **after** that tag.
   * The specific tag instance is remembered as “used.”
   * If none is found, the left boundary defaults to the start of the document (or another default rule, as implemented).

2. **Right boundary (suffix)**:

   * Scan forward from `P` for the nearest `SuffixTag` (soft or hard).
   * If found, the suffix boundary is immediately **before** that tag.
   * The specific tag instance is remembered as “used.”
   * If none is found, the right boundary defaults to the end of the document (or another default rule).

3. The context slice sent to the model is everything between the left and right boundaries, **excluding comment tags** (see §5).

After generation:

* Any **soft** prefix/suffix tags that were actually used as boundaries for this run are deleted from the document.
* Any **hard** prefix/suffix tags remain in place.
* Nested patterns:

  * Only the **nearest** prefix/suffix tags to the FIM tag (on each side) are used and possibly removed.
  * Outer tags remain untouched for later runs.

---

## 5. Comment Tags

Comment tags are annotations for humans. They are never sent to the model as context and are never auto-deleted.

### 5.1 Syntax

A comment tag is:

```ebnf
CommentTag ::= '[[' '[' '[' '(' CommentBody ')' ']' ']' ']'

CommentBody ::= { any character, including newlines, except the final ")] ] ]" terminator }
```

Example:

```text
[[[(This is a comment and will not be sent to the model.)]]]

[[[
prefix]]]
[[[(You can also use this as a block note about the section.)]]]
Actual text that the model will see.
```

Notes:

* `CommentBody` may contain newlines and arbitrary text.
* The editor treats malformed attempts (no closing `)]]]`) as plain text, not as a comment tag.

### 5.2 Semantics

When building the context slice for a FIM tag:

* **Comment tags are logically removed** from the text before computing prefix/suffix boundaries and before sending context to the model.
* In the user-visible document buffer:

  * Comment tags remain exactly as written (they are never auto-deleted).

Thus: “if it’s in a comment tag, the model does not see it.”

---

## 6. Error Handling (High-Level)

Given FIMpad’s “fail closed” philosophy:

* **Malformed FIM tag or sequence tag** (parse error):

  * Do not call the model.
  * Show an error dialog describing the problem.
* **Unknown function name**:

  * Treat as a fatal error for that tag.
* **Invalid arguments** (wrong types or arity):

  * Fatal error for that tag.
* **Duplicate `name("id")`**:

  * Mark affected FIM tags as invalid.
  * Any attempt to execute those tags or sequences referring to them results in an error.
* **Sequence uses unknown name**:

  * Error and abort the entire sequence.
* **Malformed comment** (no closing `)]]]`):

  * Treated as plain text; no special semantics.

---
