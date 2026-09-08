# Task: markdown to HTML subset

Write `run.sh` that reads `input.md` in this directory and writes
`output.html`, converting this subset: `# H1` -> `<h1>H1</h1>`,
`## H2` -> `<h2>H2</h2>`, `**bold**` -> `<strong>bold</strong>`, consecutive
lines starting with `- ` -> a `<ul>` with one `<li>` per item, and
blank-line-separated plain text lines -> `<p>...</p>`. Run the conversion
once when `run.sh` runs.
