# Task: merge conflicting note copies

Two files describe the same note: `note.md` and
`note (conflicted copy).md`. Each has `- key: value` lines. Write
`merged.md` containing the union of keys from both files as `- key: value`
lines (one per key, order doesn't matter). Where both files define the same
key with different values, keep `note.md`'s value.
