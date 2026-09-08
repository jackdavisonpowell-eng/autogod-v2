# Task: wikilink index

Scan every `.md` file in this directory (not `output.md` itself) for
`[[Target]]` and `[[Target|Display]]` wikilinks. Collect the unique set of
targets (the part before any `|`). Write `index.md`: one line per unique
target, alphabetically sorted, format `- Target` (exact target text, no
brackets). Do not include duplicates.
