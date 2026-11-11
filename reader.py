import unicodedata
#!/usr/bin/env python3
"""
manuscript_reader: A lightweight, interactive terminal reader for Markdown manuscripts.

Features:
- Paged and line-by-line reading with word wrapping adapted to terminal size
- Automatic chapter detection (markdown headers # and ##)
- Chapter jumping: Next (]), Prev ([), Table of Contents overlay (t)
- Text search (/) with forward/backward match jumping (n/N)
- Persistent reading state & bookmarks (~/.manuscript_reader_state.json)
- Help overlay (?)
- Zero external dependencies (Python 3 standard library curses)
"""

import sys
import os
import re
import json
import curses
import textwrap
from pathlib import Path

STATE_FILE = Path.home() / ".manuscript_reader_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def visual_len(text: str) -> int:
    """Return the display column width of a string (handling wide East Asian characters)."""
    w = 0
    for ch in text:
        w += 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
    return w


def wrap_visual(text: str, width: int) -> list:
    """Wrap text so that each line's visual column width does not exceed width.
    Handles both Latin space-separated words and East Asian character-level wrapping.
    """
    if width <= 0:
        width = 1
    if not text:
        return []
    if visual_len(text) <= width:
        return [text]

    lines = []
    # Tokenize: words, spaces, or individual CJK characters
    tokens = []
    current_token = []
    current_is_cjk = None

    for ch in text:
        is_cjk = unicodedata.east_asian_width(ch) in ('W', 'F')
        if is_cjk:
            if current_token:
                tokens.append(''.join(current_token))
                current_token = []
            tokens.append(ch)
            current_is_cjk = None
        elif ch.isspace():
            if current_token:
                tokens.append(''.join(current_token))
                current_token = []
            tokens.append(ch)
            current_is_cjk = None
        else:
            if current_token and current_is_cjk:
                tokens.append(''.join(current_token))
                current_token = []
            current_token.append(ch)
            current_is_cjk = False
    if current_token:
        tokens.append(''.join(current_token))

    cur_line = []
    cur_width = 0

    for tok in tokens:
        tok_w = visual_len(tok)
        # If token itself exceeds width, split character by character
        if tok_w > width:
            for sub_ch in tok:
                sc_w = visual_len(sub_ch)
                if cur_width + sc_w > width:
                    if cur_line:
                        lines.append(''.join(cur_line).rstrip())
                        cur_line = []
                        cur_width = 0
                cur_line.append(sub_ch)
                cur_width += sc_w
            continue

        if cur_width + tok_w <= width:
            cur_line.append(tok)
            cur_width += tok_w
        else:
            # Need to wrap
            if cur_line:
                lines.append(''.join(cur_line).rstrip())
                cur_line = []
                cur_width = 0
            if tok.isspace():
                # skip leading whitespace on wrapped line
                continue
            cur_line.append(tok)
            cur_width = tok_w

    if cur_line:
        lines.append(''.join(cur_line).rstrip())

    return [l for l in lines if l] or ['']


class Document:
    def __init__(self, filepath):
        self.filepath = os.path.abspath(filepath)
        self.filename = os.path.basename(filepath)
        self.raw_lines = []
        self.chapters = []  # list of (raw_line_idx, heading_level, title)
        self.title = self.filename
        self.load()

    def load(self):
        with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
            self.raw_lines = [line.rstrip("\r\n") for line in f]

        # Extract title and chapters
        in_yaml = False
        for idx, line in enumerate(self.raw_lines):
            stripped = line.strip()
            if idx == 0 and stripped == "---":
                in_yaml = True
                continue
            if in_yaml:
                if stripped == "---":
                    in_yaml = False
                continue

            m = re.match(r'^(#{1,3})\s+(.*)$', line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                if level == 1 and self.title == self.filename:
                    self.title = title
                self.chapters.append((idx, level, title))

class FormattedDocument:
    """Reflows document for a specific terminal width, tracking chapter and raw line mappings."""
    def __init__(self, doc: Document, width: int):
        self.doc = doc
        self.width = max(20, width)
        self.lines = []           # List of (formatted_text, style, raw_line_idx)
        self.chapter_line_map = {} # chapter_index -> formatted_line_idx
        self.raw_to_fmt = {}      # raw_line_idx -> formatted_line_idx
        self.fmt_to_raw = []      # formatted_line_idx -> raw_line_idx
        self.reflow()

    def reflow(self):
        self.lines = []
        self.chapter_line_map = {}
        self.raw_to_fmt = {}
        self.fmt_to_raw = []

        # Map raw chapter indices to chapter objects
        raw_chap_map = {raw_idx: (chap_idx, level, title)
                        for chap_idx, (raw_idx, level, title) in enumerate(self.doc.chapters)}

        in_yaml = False
        text_width = max(10, self.width - 2)

        for raw_idx, line in enumerate(self.doc.raw_lines):
            stripped = line.strip()
            if raw_idx == 0 and stripped == "---":
                in_yaml = True
                continue
            if in_yaml:
                if stripped == "---":
                    in_yaml = False
                continue

            # Record mapping from raw line to first formatted line
            current_fmt_idx = len(self.lines)
            self.raw_to_fmt[raw_idx] = current_fmt_idx

            if raw_idx in raw_chap_map:
                chap_idx, level, title = raw_chap_map[raw_idx]
                self.chapter_line_map[chap_idx] = current_fmt_idx
                
                # Visual separator before headings
                if current_fmt_idx > 0:
                    self.lines.append(("", "normal", raw_idx))
                    self.fmt_to_raw.append(raw_idx)
                
                style = "heading1" if level == 1 else ("heading2" if level == 2 else "heading3")
                prefix = "# " if level == 1 else ("## " if level == 2 else "### ")
                full_h = prefix + title
                wrapped = wrap_visual(full_h, width=text_width) or [full_h]
                for hline in wrapped:
                    self.lines.append((hline, style, raw_idx))
                    self.fmt_to_raw.append(raw_idx)
                self.lines.append(("", "normal", raw_idx))
                self.fmt_to_raw.append(raw_idx)
                continue

            if not stripped:
                self.lines.append(("", "normal", raw_idx))
                self.fmt_to_raw.append(raw_idx)
                continue

            # Check for quote, list item, or ordinary text
            if stripped.startswith(">"):
                quote_text = stripped[1:].strip()
                wrapped = wrap_visual(quote_text, width=max(10, text_width - 4))
                for ql in (wrapped or [""]):
                    self.lines.append(("    | " + ql, "quote", raw_idx))
                    self.fmt_to_raw.append(raw_idx)
            elif stripped.startswith("- ") or stripped.startswith("* "):
                bullet = stripped[:2]
                rest = stripped[2:].strip()
                wrapped = wrap_visual(rest, width=max(10, text_width - 4))
                if wrapped:
                    self.lines.append(("  " + bullet + wrapped[0], "bullet", raw_idx))
                    self.fmt_to_raw.append(raw_idx)
                    for item_line in wrapped[1:]:
                        self.lines.append(("    " + item_line, "bullet", raw_idx))
                        self.fmt_to_raw.append(raw_idx)
                else:
                    self.lines.append(("  " + bullet, "bullet", raw_idx))
                    self.fmt_to_raw.append(raw_idx)
            else:
                wrapped = wrap_visual(line, width=text_width)
                for w in wrapped:
                    self.lines.append((w, "normal", raw_idx))
                    self.fmt_to_raw.append(raw_idx)

    def get_current_chapter(self, fmt_line_idx):
        if not self.doc.chapters:
            return None
        last_chap = self.doc.chapters[0]
        for chap_idx, (raw_idx, level, title) in enumerate(self.doc.chapters):
            f_idx = self.chapter_line_map.get(chap_idx, 0)
            if f_idx <= fmt_line_idx:
                last_chap = (raw_idx, level, title)
            else:
                break
        return last_chap

    def get_next_chapter_line(self, fmt_line_idx):
        for chap_idx, (raw_idx, level, title) in enumerate(self.doc.chapters):
            f_idx = self.chapter_line_map.get(chap_idx, 0)
            if f_idx > fmt_line_idx:
                return f_idx
        return None

    def get_prev_chapter_line(self, fmt_line_idx):
        prev = None
        for chap_idx, (raw_idx, level, title) in enumerate(self.doc.chapters):
            f_idx = self.chapter_line_map.get(chap_idx, 0)
            if f_idx < fmt_line_idx - 1:
                prev = f_idx
            else:
                break
        return prev

class ManuscriptReader:
    def __init__(self, filepath):
        self.doc = Document(filepath)
        self.state = load_state()
        self.file_state = self.state.get(self.doc.filepath, {})
        
        # Restore raw line or default to 0
        self.current_raw_line = self.file_state.get("last_raw_line", 0)
        self.bookmarks = self.file_state.get("bookmarks", {}) # label -> raw_line
        
        self.search_term = ""
        self.search_matches = [] # list of fmt_line_idx
        self.search_match_cursor = -1

    def save(self, top_fmt_idx, fmt_doc):
        raw_idx = fmt_doc.fmt_to_raw[top_fmt_idx] if 0 <= top_fmt_idx < len(fmt_doc.fmt_to_raw) else 0
        self.file_state["last_raw_line"] = raw_idx
        self.file_state["bookmarks"] = self.bookmarks
        self.state[self.doc.filepath] = self.file_state
        save_state(self.state)

    def run(self):
        curses.wrapper(self._main_loop)

    def _main_loop(self, stdscr):
        curses.raw()
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)
        has_colors = False
        try:
            if curses.has_colors():
                curses.start_color()
                bg_color = curses.COLOR_BLACK
                try:
                    curses.use_default_colors()
                    bg_color = -1
                except Exception:
                    pass
                curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
                curses.init_pair(2, curses.COLOR_YELLOW, bg_color)
                curses.init_pair(3, curses.COLOR_GREEN, bg_color)
                curses.init_pair(4, curses.COLOR_MAGENTA, bg_color)
                curses.init_pair(5, curses.COLOR_BLUE, bg_color)
                curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_YELLOW)
                curses.init_pair(7, curses.COLOR_WHITE, bg_color)
                has_colors = True
        except Exception:
            pass

        max_y, max_x = stdscr.getmaxyx()
        fmt_doc = FormattedDocument(self.doc, max_x)
        
        # Translate initial raw line to formatted line
        top_line = fmt_doc.raw_to_fmt.get(self.current_raw_line, 0)
        status_message = "Press '?' for Help | 't' for Table of Contents | '/' to Search | 'q' to Quit"

        while True:
            cur_y, cur_x = stdscr.getmaxyx()
            if cur_y != max_y or cur_x != max_x:
                max_y, max_x = cur_y, cur_x
                # Re-reflow to new terminal dimensions
                cur_raw = fmt_doc.fmt_to_raw[top_line] if top_line < len(fmt_doc.fmt_to_raw) else 0
                fmt_doc = FormattedDocument(self.doc, max_x)
                top_line = fmt_doc.raw_to_fmt.get(cur_raw, 0)
                stdscr.clear()

            content_height = max_y - 2
            total_lines = len(fmt_doc.lines)
            if top_line > total_lines - content_height:
                top_line = max(0, total_lines - content_height)
            if top_line < 0:
                top_line = 0

            # Render Screen
            stdscr.erase()

            # 1. Header Bar
            cur_chap = fmt_doc.get_current_chapter(top_line)
            chap_title = cur_chap[2] if cur_chap else "Front Matter"
            header_text = f" {self.doc.title} » {chap_title}"
            if len(header_text) > max_x:
                header_text = header_text[:max_x - 1]
            try:
                stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
                stdscr.addstr(0, 0, header_text.ljust(max_x))
                stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
            except curses.error:
                pass

            # 2. Content Area
            for row in range(content_height):
                line_idx = top_line + row
                if line_idx >= total_lines:
                    break
                text, style, raw_idx = fmt_doc.lines[line_idx]
                screen_y = row + 1

                attr = curses.A_NORMAL
                color = 0
                if style == "heading1":
                    attr = curses.A_BOLD | curses.A_UNDERLINE
                    color = curses.color_pair(2)
                elif style == "heading2":
                    attr = curses.A_BOLD
                    color = curses.color_pair(3)
                elif style == "heading3":
                    attr = curses.A_BOLD
                    color = curses.color_pair(4)
                elif style == "quote":
                    attr = curses.A_ITALIC if hasattr(curses, "A_ITALIC") else curses.A_NORMAL
                    color = curses.color_pair(5)

                try:
                    display_text = text[:max_x - 1]
                    if self.search_term and self.search_term.lower() in display_text.lower():
                        # Simple highlight search match
                        stdscr.addstr(screen_y, 1, display_text)
                    else:
                        stdscr.addstr(screen_y, 1, display_text, color | attr)
                except curses.error:
                    pass

            # 3. Status Bar
            pct = 100 if total_lines <= content_height else int((top_line / (total_lines - content_height)) * 100)
            pct = min(100, max(0, pct))
            raw_cur = fmt_doc.fmt_to_raw[top_line] if top_line < len(fmt_doc.fmt_to_raw) else 0
            status_right = f" Line {raw_cur+1}/{len(self.doc.raw_lines)} ({pct}%) "
            status_left = f" {status_message}"
            available_left = max_x - len(status_right) - 1
            if available_left > 0:
                bar = (status_left[:available_left]).ljust(available_left) + status_right
            else:
                bar = status_right.rjust(max_x)

            try:
                stdscr.attron(curses.color_pair(1))
                stdscr.addstr(max_y - 1, 0, bar[:max_x])
                stdscr.attroff(curses.color_pair(1))
            except curses.error:
                pass

            stdscr.refresh()

            # Handle Key Input
            try:
                ch = stdscr.get_wch()
            except curses.error:
                continue

            status_message = "Press '?' for Help | 't' for Table of Contents | '/' to Search | 'q' to Quit"

            if ch in ('q', 'Q', 27):  # Quit on q or Esc
                self.save(top_line, fmt_doc)
                break

            elif ch in ('j', curses.KEY_DOWN):
                if top_line < total_lines - content_height:
                    top_line += 1
            elif ch in ('k', curses.KEY_UP):
                if top_line > 0:
                    top_line -= 1
            elif ch in (' ', curses.KEY_NPAGE, 'f'):  # Page Down
                top_line = min(total_lines - content_height, top_line + content_height - 1)
            elif ch in ('b', curses.KEY_PPAGE):      # Page Up
                top_line = max(0, top_line - (content_height - 1))
            elif ch in ('d', 4):                      # Half page down (Ctrl-D or 'd')
                top_line = min(total_lines - content_height, top_line + content_height // 2)
            elif ch in ('u', 21):                     # Half page up (Ctrl-U or 'u')
                top_line = max(0, top_line - content_height // 2)
            elif ch in ('g', curses.KEY_HOME):       # Beginning
                top_line = 0
            elif ch in ('G', curses.KEY_END):        # End
                top_line = max(0, total_lines - content_height)

            elif ch in (']', 'n', 'J'):              # Next Chapter
                nxt = fmt_doc.get_next_chapter_line(top_line)
                if nxt is not None:
                    top_line = nxt
                    status_message = "Jumped to Next Chapter"
                else:
                    status_message = "Already at the last chapter"
            elif ch in ('[', 'p', 'K'):              # Previous Chapter
                prv = fmt_doc.get_prev_chapter_line(top_line)
                if prv is not None:
                    top_line = prv
                    status_message = "Jumped to Previous Chapter"
                else:
                    status_message = "Already at the first chapter"

            elif ch in ('t', 'T', 9):                # Table of Contents
                sel = self.show_toc(stdscr, fmt_doc)
                if sel is not None:
                    top_line = fmt_doc.chapter_line_map.get(sel, 0)
                    status_message = f"Jumped to: {self.doc.chapters[sel][2]}"

            elif ch == 'm':                          # Add bookmark
                name = self.prompt_text(stdscr, "Bookmark name (leave empty for quick-mark):")
                if name is not None:
                    label = name.strip() or f"Mark at line {raw_cur+1}"
                    self.bookmarks[label] = raw_cur
                    self.save(top_line, fmt_doc)
                    status_message = f"Bookmark saved: '{label}'"
            elif ch in ("'", 'B'):                   # Jump to bookmark
                sel_raw = self.show_bookmarks(stdscr)
                if sel_raw is not None:
                    top_line = fmt_doc.raw_to_fmt.get(sel_raw, 0)
                    status_message = f"Jumped to bookmark at line {sel_raw+1}"

            elif ch == '/':                          # Search
                query = self.prompt_text(stdscr, "Search text:")
                if query:
                    self.search_term = query
                    self.search_matches = [
                        idx for idx, (text, _, _) in enumerate(fmt_doc.lines)
                        if query.lower() in text.lower()
                    ]
                    if self.search_matches:
                        # Find first match >= top_line
                        found = False
                        for m_idx, line_idx in enumerate(self.search_matches):
                            if line_idx >= top_line:
                                self.search_match_cursor = m_idx
                                top_line = line_idx
                                found = True
                                break
                        if not found:
                            self.search_match_cursor = 0
                            top_line = self.search_matches[0]
                        status_message = f"Search '{query}': match {self.search_match_cursor+1}/{len(self.search_matches)} (Press 'n'/'N')"
                    else:
                        status_message = f"Pattern not found: '{query}'"
            elif ch == '?':                          # Help overlay
                self.show_help(stdscr)

    def prompt_text(self, stdscr, prompt):
        max_y, max_x = stdscr.getmaxyx()
        curses.echo()
        curses.curs_set(1)
        try:
            stdscr.attron(curses.color_pair(1))
            stdscr.addstr(max_y - 1, 0, f" {prompt} ".ljust(max_x))
            stdscr.attroff(curses.color_pair(1))
            stdscr.refresh()
            buf = stdscr.getstr(max_y - 1, len(prompt) + 2, max_x - len(prompt) - 3)
            return buf.decode("utf-8", errors="replace")
        except Exception:
            return None
        finally:
            curses.noecho()
            curses.curs_set(0)

    def show_toc(self, stdscr, fmt_doc):
        """Interactive chapter table of contents picker."""
        if not self.doc.chapters:
            return None
        cursor = 0
        scroll_offset = 0
        
        while True:
            max_y, max_x = stdscr.getmaxyx()
            box_height = max(5, max_y - 4)
            box_width = min(max_x - 4, 100)
            start_y = 2
            start_x = (max_x - box_width) // 2

            stdscr.erase()
            # Title header
            stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
            stdscr.addstr(start_y, start_x, " Table of Contents (Enter: Select | Up/Down: Navigate | Esc: Cancel) ".center(box_width))
            stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

            visible_rows = box_height - 2
            if cursor < scroll_offset:
                scroll_offset = cursor
            elif cursor >= scroll_offset + visible_rows:
                scroll_offset = cursor - visible_rows + 1

            for i in range(visible_rows):
                idx = scroll_offset + i
                if idx >= len(self.doc.chapters):
                    break
                raw_idx, level, title = self.doc.chapters[idx]
                indent = "  " * (level - 1)
                item_str = f" {indent}{title}"[:box_width - 2].ljust(box_width - 2)
                y = start_y + 1 + i
                if idx == cursor:
                    stdscr.attron(curses.color_pair(6) | curses.A_BOLD)
                    stdscr.addstr(y, start_x + 1, item_str)
                    stdscr.attroff(curses.color_pair(6) | curses.A_BOLD)
                else:
                    color = curses.color_pair(3) if level == 2 else curses.color_pair(2)
                    stdscr.addstr(y, start_x + 1, item_str, color)

            stdscr.refresh()
            ch = stdscr.get_wch()
            if ch in (27, 'q', 'Q'):
                return None
            elif ch in (curses.KEY_UP, 'k'):
                cursor = max(0, cursor - 1)
            elif ch in (curses.KEY_DOWN, 'j'):
                cursor = min(len(self.doc.chapters) - 1, cursor + 1)
            elif ch in (curses.KEY_PPAGE, 'b'):
                cursor = max(0, cursor - visible_rows)
            elif ch in (curses.KEY_NPAGE, ' '):
                cursor = min(len(self.doc.chapters) - 1, cursor + visible_rows)
            elif ch in ('\n', '\r', curses.KEY_ENTER):
                return cursor

    def show_bookmarks(self, stdscr):
        """Interactive bookmarks list."""
        if not self.bookmarks:
            return None
        items = list(self.bookmarks.items())
        cursor = 0
        while True:
            max_y, max_x = stdscr.getmaxyx()
            box_width = min(max_x - 4, 80)
            box_height = min(max_y - 4, len(items) + 4)
            start_y = (max_y - box_height) // 2
            start_x = (max_x - box_width) // 2

            stdscr.erase()
            stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
            stdscr.addstr(start_y, start_x, " Bookmarks (Enter: Jump | d: Delete | Esc: Cancel) ".center(box_width))
            stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

            for i, (label, raw_idx) in enumerate(items):
                y = start_y + 1 + i
                text = f" {label} (raw line {raw_idx+1})"[:box_width-2].ljust(box_width-2)
                if i == cursor:
                    stdscr.attron(curses.color_pair(6) | curses.A_BOLD)
                    stdscr.addstr(y, start_x + 1, text)
                    stdscr.attroff(curses.color_pair(6) | curses.A_BOLD)
                else:
                    stdscr.addstr(y, start_x + 1, text)

            stdscr.refresh()
            ch = stdscr.get_wch()
            if ch in (27, 'q', 'Q'):
                return None
            elif ch in (curses.KEY_UP, 'k'):
                cursor = max(0, cursor - 1)
            elif ch in (curses.KEY_DOWN, 'j'):
                cursor = min(len(items) - 1, cursor + 1)
            elif ch in ('d', curses.KEY_DC):
                # Delete bookmark
                del_label, _ = items[cursor]
                del self.bookmarks[del_label]
                items = list(self.bookmarks.items())
                if not items:
                    return None
                cursor = min(cursor, len(items) - 1)
            elif ch in ('\n', '\r', curses.KEY_ENTER):
                return items[cursor][1]

    def show_help(self, stdscr):
        """Displays help screen."""
        max_y, max_x = stdscr.getmaxyx()
        box_width = min(max_x - 4, 78)
        help_lines = [
            "Manuscript Reader - Key Controls",
            "--------------------------------------------------",
            " Navigation:",
            "   j / Down         : Scroll down 1 line",
            "   k / Up           : Scroll up 1 line",
            "   Space / PageDown : Scroll down 1 page",
            "   b / PageUp       : Scroll up 1 page",
            "   d / u            : Half-page down / up",
            "   g / Home         : Jump to top of document",
            "   G / End          : Jump to end of document",
            "",
            " Chapters & Bookmarks:",
            "   ] / n            : Next chapter",
            "   [ / p            : Previous chapter",
            "   t / Tab          : Open Table of Contents overlay",
            "   m                : Save named or quick bookmark",
            "   ' / B            : Open Bookmarks manager / jump",
            "",
            " Search & Misc:",
            "   /                : Search text",
            "   ?                : This help screen",
            "   q / Esc          : Save state & Quit",
            "--------------------------------------------------",
            " Press any key to return to reading..."
        ]
        start_y = max(1, (max_y - len(help_lines)) // 2)
        start_x = max(1, (max_x - box_width) // 2)

        stdscr.erase()
        for idx, line in enumerate(help_lines):
            try:
                y = start_y + idx
                if idx == 0:
                    stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
                    stdscr.addstr(y, start_x, line.center(box_width))
                    stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
                elif line.startswith(" Navigation:") or line.startswith(" Chapters") or line.startswith(" Search"):
                    stdscr.addstr(y, start_x, line, curses.color_pair(2) | curses.A_BOLD)
                else:
                    stdscr.addstr(y, start_x, line)
            except curses.error:
                pass
        stdscr.refresh()
        stdscr.get_wch()

def main():
    if len(sys.argv) < 2:
        default_path = "/Users/cat/Downloads/Oasis.md"
        if os.path.exists(default_path):
            filepath = default_path
        else:
            print("Usage: python3 reader.py <path_to_markdown_file>")
            sys.exit(1)
    else:
        filepath = sys.argv[1]

    if not os.path.isfile(filepath):
        print(f"Error: File '{filepath}' does not exist.")
        sys.exit(1)

    reader = ManuscriptReader(filepath)
    reader.run()

if __name__ == "__main__":
    main()
