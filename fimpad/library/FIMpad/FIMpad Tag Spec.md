# FIMpad Tag Specification

## 0. Tag Types

All FIMpad tags start with `[[[` and end with `]]]`. The first character **after** `[[[` determines the kind of tag:

* **Digit** (`0–9`) → **FIM tag** (generation tag)
* **Left parenthesis** (`(`) → **Comment tag**
* **Left brace** (`{`) → **Config tag** (settings preset)
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
* String literals (used inside functions):

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
  [[[100;stop("User: ");chop("END");append("Done.\n")]]]
  ```

A FIM tag can be formatted across multiple lines for readability:

```text
[[[
  100;
  stop("User: ");
  chop("END_OF_SECTION");
  append("That is my final answer.\n");
]]]
```

Whitespace and newlines are ignored between tokens.

### 2.2 Functions and Phases

Each function belongs to **one** of two conceptual phases:

* **Init-time (before streaming / request configuration)**
  Evaluated in order before calling the model.

  * `stop(pattern1, pattern2, ...)`
  * `chop(pattern1, pattern2, ...)`
  * `temp(float)`
  * `top_p(float)`

  Use `temp("0.5")` or `top_p("0.8")` to override the corresponding
  sampling settings for a single FIM tag.

* **Post-time (after streaming completes)**
  Evaluated in order on the final generated text.

  * `append(string)`

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

---

## 3. Prefix / Suffix Tags

Prefix/suffix tags define context windows for FIM tags. There are **soft** (lowercase) and **hard** (uppercase) variants.

### 3.1 Syntax

```ebnf
PrefixTag ::= '[[[' ('prefix' | 'PREFIX') ']' ']' ']'
SuffixTag ::= '[[[' ('suffix' | 'SUFFIX') ']' ']' ']'
```

Accepted forms:

* Soft prefix: `[[[prefix]]]`
* Hard prefix: `[[[PREFIX]]]`
* Soft suffix: `[[[suffix]]]`
* Hard suffix: `[[[SUFFIX]]]`

### 3.2 Soft vs Hard Semantics

* **Soft** tags (`prefix`, `suffix`):

  * May be *auto-deleted* after generation when they are used.
* **Hard** tags (`PREFIX`, `SUFFIX`):

  * Are **never** auto-deleted.

### 3.3 How FIM Tags Use Prefix/Suffix

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

3. The context slice sent to the model is everything between the left and right boundaries, **excluding comment tags** (see §4).

After generation:

* Any **soft** prefix/suffix tags that were actually used as boundaries for this run are deleted from the document.
* Any **hard** prefix/suffix tags remain in place.
* Nested patterns:

  * Only the **nearest** prefix/suffix tags to the FIM tag (on each side) are used and possibly removed.
  * Outer tags remain untouched for later runs.

---

## 4. Comment Tags

Comment tags are annotations for humans. They are never sent to the model as context and are never auto-deleted.

### 4.1 Syntax

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

### 4.2 Semantics

When building the context slice for a FIM tag:

* **Comment tags are logically removed** from the text before computing prefix/suffix boundaries and before sending context to the model.
* In the user-visible document buffer:

  * Comment tags remain exactly as written (they are never auto-deleted).

Thus: “if it’s in a comment tag, the model does not see it.”

---

## 5. Config Tags (Settings Presets)

Config tags apply editor settings without running the model. They may be inline or multiline and are triggered when the caret is inside or adjacent to the tag and the user generates.

### 5.1 Syntax

```
ConfigTag ::= '[[' '[' '[' WS? '{' ConfigBody '}' WS? ']' ']' ']'

ConfigBody ::= ConfigEntry (';' WS? ConfigEntry)* ';'?
ConfigEntry ::= ConfigKey WS? ':' WS? STRING
ConfigKey   ::= IDENT  (use camelCase for readability)
```

Example:

```text
[[[{font:"Ubuntu Sans"; fontSize:"24"; bgColor:"#141414"; fgColor:"#f5f5f5"}]]]
```

### 5.2 Supported Keys

Each entry mirrors a Settings window field (values are the text you would type there). Recognized keys:

* `endpoint`, `temperature`, `topP`
* `fimPrefix`, `fimSuffix`, `fimMiddle`
* `font`/`fontFamily`, `fontSize`
* `editorPadding`, `lineNumberPadding`
* `fgColor`, `bgColor`, `caretColor`, `selectionColor`
* `scrollSpeed`
* `spellLang`

The `open_maximized` setting **cannot** be changed via config tags.

### 5.3 Semantics

* All values must be quoted strings.
* Numeric fields are validated (floats for temperature/topP; integers with bounds for sizes and padding).
* Colors must be valid Tk color strings; otherwise an error is shown and nothing changes.
* Fonts and spellcheck languages are validated against what the system provides. Missing fonts/languages produce an error and no settings are applied.
* On success, the settings are applied immediately (as if saved from the Settings window) and persisted to the config file. The config tag itself remains in the document.

---

## 6. Error Handling (High-Level)

Given FIMpad’s “fail closed” philosophy:

* **Malformed FIM tag** (parse error):

  * Do not call the model.
  * Show an error dialog describing the problem.
* **Unknown function name**:

  * Treat as a fatal error for that tag.
* **Invalid arguments** (wrong types or arity):

  * Mark affected FIM tags as invalid.
* **Malformed comment** (no closing `)]]]`):

  * Treated as plain text; no special semantics.

---
