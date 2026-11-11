import os
import sys
import json
import tempfile
import reader

MANUSCRIPT = "/Users/cat/Downloads/Oasis.md"

def test_document_loading():
    print("Testing document loading...")
    assert os.path.exists(MANUSCRIPT), f"File {MANUSCRIPT} does not exist"
    doc = reader.Document(MANUSCRIPT)
    assert doc.title == "Oasis: Between Heaven and Man", f"Unexpected title: {doc.title}"
    assert len(doc.raw_lines) > 6000, f"Expected >6000 raw lines, got {len(doc.raw_lines)}"
    assert len(doc.chapters) >= 76, f"Expected >= 76 chapters, got {len(doc.chapters)}"
    print(f"  OK: Loaded {len(doc.raw_lines)} lines, title: '{doc.title}', {len(doc.chapters)} chapters detected.")

def test_formatted_document():
    print("Testing document formatting & word-wrapping at 80 cols...")
    doc = reader.Document(MANUSCRIPT)
    fmt = reader.FormattedDocument(doc, width=80)
    assert len(fmt.lines) > len(doc.raw_lines), f"Formatted lines ({len(fmt.lines)}) should exceed raw lines ({len(doc.raw_lines)})"
    assert len(fmt.fmt_to_raw) == len(fmt.lines)
    assert len(fmt.chapter_line_map) == len(doc.chapters)
    print(f"  OK: Formatted to {len(fmt.lines)} display lines.")

def test_navigation_and_chapters():
    print("Testing chapter navigation...")
    doc = reader.Document(MANUSCRIPT)
    fmt = reader.FormattedDocument(doc, width=80)
    
    # Title is at line 1, Chapter 1 is at line 12
    first_heading = fmt.get_next_chapter_line(0)
    assert first_heading == 1, f"Expected first heading line 1, got {first_heading}"
    ch1_line = fmt.get_next_chapter_line(1)
    assert ch1_line == 12, f"Expected Chapter 1 at line 12, got {ch1_line}"
    
    chap = fmt.get_current_chapter(ch1_line)
    assert chap is not None and "Chapter 1" in chap[2], f"Expected Chapter 1, got {chap}"
    
    prev_line = fmt.get_prev_chapter_line(ch1_line)
    assert prev_line == 1, f"Expected previous heading line 1, got {prev_line}"
    print("  OK: Next/prev chapter navigation logic verified.")

def test_state_and_bookmarks():
    print("Testing state persistence & bookmarks...")
    # Test saving state to custom state file path by temporarily overriding STATE_FILE
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        temp_state_file = tf.name
    
    orig_state_file = reader.STATE_FILE
    reader.STATE_FILE = temp_state_file
    try:
        r = reader.ManuscriptReader(MANUSCRIPT)
        fmt = reader.FormattedDocument(r.doc, width=80)
        
        # Add a bookmark
        r.bookmarks["ch5"] = 250
        r.save(top_fmt_idx=250, fmt_doc=fmt)
        
        # Load state directly
        saved_state = reader.load_state()
        assert r.doc.filepath in saved_state
        entry = saved_state[r.doc.filepath]
        assert entry["bookmarks"].get("ch5") == 250
        assert "last_raw_line" in entry
        
        # Create a new reader and verify restored state
        r2 = reader.ManuscriptReader(MANUSCRIPT)
        assert r2.bookmarks.get("ch5") == 250
        print("  OK: State and bookmarks saved and restored successfully.")
    finally:
        reader.STATE_FILE = orig_state_file
        if os.path.exists(temp_state_file):
            os.remove(temp_state_file)

def test_search():
    print("Testing search logic...")
    doc = reader.Document(MANUSCRIPT)
    fmt = reader.FormattedDocument(doc, width=80)
    term = "Heaven"
    matches = [i for i, (line, style, raw_idx) in enumerate(fmt.lines) if term.lower() in line.lower()]
    assert len(matches) > 0, "Expected search matches for 'Heaven'"
    print(f"  OK: Found {len(matches)} search matches for '{term}'.")

if __name__ == "__main__":
    test_document_loading()
    test_formatted_document()
    test_navigation_and_chapters()
    test_state_and_bookmarks()
    test_search()
    print("\nALL READER TESTS PASSED SUCCESSFULLY!")
