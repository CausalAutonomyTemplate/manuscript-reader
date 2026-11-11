# Terminal Manuscript Reader

A lightweight, interactive manuscript reader for Terminal built with Python standard libraries (`curses`, `textwrap`, `json`, etc.). Designed specifically for comfortable reading of large Markdown manuscripts like *Oasis: Between Heaven and Man* or any structured document.

## Features

- **Document Parsing & Wrapping:** Automatically detects document titles and chapter headers (`#` and `##`), reflowing long paragraphs cleanly to the terminal width without cutting words.
- **Fluid Navigation:**
  - `j` / `Down`: Scroll down 1 line
  - `k` / `Up`: Scroll up 1 line
  - `d` / `Ctrl-D`: Scroll down half a page
  - `u` / `Ctrl-U`: Scroll up half a page
  - `Space` / `PageDown`: Page down
  - `b` / `PageUp`: Page up
  - `g` / `Home`: Jump to top of manuscript
  - `G` / `End`: Jump to end of manuscript
- **Chapter Navigation:**
  - `]` or `n`: Jump to next chapter
  - `[` or `p`: Jump to previous chapter
  - `t` or `c` or `Tab`: Interactive Table of Contents overlay for instant chapter selection
- **Reading Positions & Bookmarks:**
  - Automatically saves the last reading position on exit and restores it upon re-opening.
  - `m`: Set/add a named bookmark at current reading position.
  - `'` or `B`: Open interactive bookmark manager to view, jump to, or delete bookmarks.
  - State persisted per-file in `~/.manuscript_reader_state.json`.
- **Search:**
  - `/`: Prompt for search term
  - `n`: Jump to next match
  - `N`: Jump to previous match
- **UI:**
  - Top header displaying manuscript title and current active chapter.
  - Bottom status bar showing position (line number, total lines, percentage) and help shortcuts.
  - `?`: Toggle help overlay.
  - `q`: Quit.

## Quick Start

```bash
python3 reader.py /Users/cat/Downloads/Oasis.md
```
