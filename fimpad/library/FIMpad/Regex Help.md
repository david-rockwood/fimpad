# FIMpad Regex Help.md

---

## Regex & Replace in FIMpad (Python `re` syntax)

FIMpad includes a **Regex & Replace** tool for advanced searching and rewriting using **Python’s `re` regular expression syntax**.
This dialog is separate from the normal **Find & Replace** window and provides pattern-based editing capabilities.

Use regex when you want to:

* find variations of a pattern
* modify structured text
* match whole words or line boundaries
* swap or reorder text
* clean formatting or whitespace
* apply large-scale editing operations efficiently

This document introduces the essentials of Python-style regex for FIMpad users.

---

## 1. Basic Concepts

### Literal matches

Most characters match themselves:

```
cat
```

matches “cat” anywhere it appears.

### Wildcard `.`

`.` matches **any single character** except newline (unless Dot-All mode is on):

```
c.t
```

matches “cat”, “cot”, “cut”, “c t”, etc.

### Character classes `[ ... ]`

Match **one character from a set**:

* `[aeiou]` → any vowel
* `[0-9]` → any digit
* `[A-Za-z]` → any ASCII letter
* `[^0-9]` → anything **except** a digit

Example:

```
gr[ae]y
```

matches “gray” or “grey”.

---

## 2. Quantifiers

Control how many times something repeats:

* `*` → 0 or more
* `+` → 1 or more
* `?` → 0 or 1 (optional)
* `{m}` → exactly m times
* `{m,}` → m or more
* `{m,n}` → between m and n times

Examples:

```
go+gle          # gogle, google, gooogle...
ha*             # h, ha, haa, haaa...
\d{4}           # exactly 4 digits
```

### Greedy vs non-greedy

Quantifiers are greedy by default:

```
".*"
```

matches the longest possible quoted region.

Add `?` for a non-greedy match:

```
".*?"
```

matches the shortest possible one.

---

## 3. Anchors and Boundaries

### Word boundary: `\b`

Matches between a word character and a non-word character.

```
\bcat\b
```

matches “cat” as a whole word, not “concatenate”.

### Line anchors: `^` and `$`

* `^` matches start of line
* `$` matches end of line

With **Multiline** enabled in FIMpad, these anchors apply to *every* line.

Examples:

```
^#           # lines beginning with #
;$           # lines ending with ;
```

---

## 4. Groups and Alternation

### Capturing groups `( ... )`

Parentheses **group** part of the pattern and capture it for reuse:

```
(\w+)\s+(\w+)
```

Captures two words:

* Group 1: first word
* Group 2: second word

### Alternation `|`

Matches X **or** Y:

```
(cat|dog)
```

```
(Mr|Ms|Dr)\. \w+
```

---

## 5. Replacement Syntax

In FIMpad’s **Replacement** field, you can insert captured groups using Python’s `re.sub` notation:

* `\1`, `\2` → first and second group
* `\g<1>` → same as `\1`
* `\g<name>` → named groups (optional feature)

### Examples

Swap two words:

```
Pattern:     (\w+)\s+(\w+)
Replacement: \2 \1
```

Turn “Key: Value” into JSON-like format:

```
Pattern:     ^([^:]+):\s*(.+)$
Replacement: "\1": "\2",
Flags:       Multiline
```

Add quotes around a word:

```
Pattern:     \b(cat)\b
Replacement: "\1"
```

---

## 6. Regex Flags (the checkboxes)

FIMpad provides three common flags:

### ✔ Ignore case — `re.IGNORECASE`

`cat` matches `Cat`, `CAT`, `cAt`, etc.

### ✔ Multiline (^ and $ match each line) — `re.MULTILINE`

`^` and `$` anchor to lines within the text, not just the entire document.

### ✔ Dot matches newline — `re.DOTALL`

`.` matches newline characters too, allowing multi-line patterns like:

```
<begin>.*?<end>
```

to work across several lines.

---

## 7. Escaping Special Characters

These characters have special meaning:

```
. * + ? ( ) [ ] { } | ^ $ \
```

To search for them literally, prefix with `\`:

```
\.   # literal dot
\?   # literal question mark
\[   # literal [
```

---

## 8. Useful Recipes for FIMpad Users

### Add “- ” to the start of every line

```
Pattern:      ^
Replacement:  - 
Flags:        Multiline
```

### Collapse multiple spaces into one

```
Pattern:      [ ]+
Replacement:  (single space)
```

### Remove trailing whitespace per line

```
Pattern:      [ \t]+$
Replacement:  (empty)
Flags:        Multiline
```

### Swap first and last name

```
Pattern:      (\w+)\s+(\w+)
Replacement:  \2, \1
```

### Extract sentences between tags

```
Pattern:      <start>(.*?)<end>
Flags:        Dot matches newline (if needed)
```

### Convert bullet list to numbered list

```
Pattern:      ^[-*]\s+
Replacement:  1. 
Flags:        Multiline
```

(Afterward you can renumber with another pass.)

---

## 9. Tips and Gotchas

* **Use “Find next” first** to preview what your regex matches.
* If a match “eats too much,” try making the quantifier non-greedy (`.*?`).
* `\n` and `\t` in the replacement field insert actual newlines and tabs.
* Use `\\n` if you want a literal “\n”.

If the pattern is invalid, FIMpad will show a message and will not modify your document.

---

## 10. Summary

Regex & Replace in FIMpad lets you:

* match complex patterns
* leverage groups to reorganize text
* perform large-scale, structured edits
* use Python’s proven `re` engine
* apply flags for case handling, multiline anchors, and dot behavior

For most tasks, a pattern + groups + replacement + flags gives you powerful control without complexity.

If you’re new to regex, start with simple patterns and experiment with **Find next** before doing **Replace all**.
