# gloss

A desktop app for taking notes during lectures — with AI review built in after class.

You view your professor's slides on the left, take notes on the right using a simple
markup syntax, and when you're done, enter Review Mode to have an LLM go through your
notes against the full slide deck. It answers your questions, catches misconceptions,
and lets you ask follow-up questions on any response.

The name comes from the scholarly term *gloss* — a marginal annotation written
alongside a text.

---

## Setup

```bash
git clone https://github.com/marcosdiazvazquez/gloss
cd gloss
pip install -r requirements.txt
python main.py
```

Python 3.11+ required.

---

## How it works

1. **Create a course** from the home screen (e.g. "CISC 361")
2. **Add a lecture** — pick a PDF and give it a title
3. **Take notes** while viewing the slides using the markup syntax below
4. **Finalize** your notes when you're done — this locks editing and enables Review Mode
5. **Enter Review Mode** — the app sends your notes + full PDF to an LLM and displays responses inline
6. **Follow up** on any response by clicking "Follow up" on a card

Notes auto-save on every keystroke. There is no save button.

---

## Markup syntax

Prefix any line with a symbol to tell the LLM how to handle it:

| Symbol | Meaning | What the LLM does |
|--------|---------|-------------------|
| `-` | General note | Checks it for accuracy against the slides |
| `?` | Question | Answers it using the slide content |
| `~` | Uncertain | Confirms or corrects your understanding |
| `!` | Important | Gives a focused summary of the related concepts |

```
- Merge sort: divide, sort halves, then merge. Always O(n log n).
? Why is O(n log n) the lower bound for comparison sorts?
~ I think quicksort is always O(n log n)?
! Professor said this will be on the midterm
```

---

## LLM configuration

Open settings (⚙ icon on the home screen) to enter your API key and pick a provider.

**Anthropic (Claude)**
Get a key at [console.anthropic.com](https://console.anthropic.com). Models: Opus 4.6, Sonnet 4, Haiku 4.

**OpenAI**
Get a key at [platform.openai.com](https://platform.openai.com). Models: o1, GPT-4o, o3-mini, GPT-4o mini.

**Google Gemini**
Get a key at [aistudio.google.com](https://aistudio.google.com). Models: Gemini 2.5 Pro, 2.5 Flash, 2.5 Flash Lite.

Each provider receives the full lecture PDF alongside your notes, so the LLM has
complete context for every response.

---

## Data storage

Notes and sessions are stored locally as JSON files:

- **macOS:** `~/Library/Application Support/gloss/`
- **Windows:** `%LOCALAPPDATA%/gloss/`
- **Linux:** `~/.local/share/gloss/`

---

## License

MIT
