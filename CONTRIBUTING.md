# Contributing to FIMpad

FIMpad is primarily a personal / experimental project. I build it for my own workflows and use it as a playground for ideas about FIM (fill-in-the-middle) prompting and local LLM tooling.

That said, small contributions are welcome if they align with the project’s direction.

---

## What kind of contributions are welcome?

- **Bug reports**  
  - Crashes, tracebacks, obvious broken behavior.
  - Wrong or surprising behavior in FIM or chat handling.
  - Repro steps are very helpful.

- **Small, focused improvements**
  - Clear bug fixes.
  - Typos or small documentation fixes.
  - Minimal UI / UX tweaks with a clear motivation.

- **Discussions / ideas (via issues)**
  - Suggestions for FIM workflows.
  - Ideas that simplify the code or user experience.

---

## What I’m *not* looking for (right now)

To keep the project manageable, I’m generally **not** looking for:

- Large new features or complete rewrites.
- Major architectural changes.
- Big dependency additions.
- Platform-specific hacks that make other platforms worse.

If you’re thinking about a bigger change, please **open an issue first** so we can see if it fits the project.

---

## Development setup

FIMpad is written in Python and currently targets Linux (and possibly other Unix-like systems).

Clone the repo and set up a virtual environment:

```
bash
git clone https://github.com/david-rockwood/fimpad.git
cd fimpad

python3 -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
```

---

## The overall scope of FIMpad

- Lightweight editor

- FIM generation only. No (system prompt / user prompt / assistant response) chats.

- No heavy dependencies

- Python-only

- Local LLM workflow assumed

