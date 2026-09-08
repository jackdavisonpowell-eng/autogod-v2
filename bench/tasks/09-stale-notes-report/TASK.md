# Task: stale notes report

Today is 2026-09-08. Each `.md` file in this directory has YAML
frontmatter with an `updated: YYYY-MM-DD` field. Write `stale.md` listing
every note whose `updated` date is more than 30 days before today, sorted
oldest first, one per line: `- filename (updated: YYYY-MM-DD)`. Notes
updated 30 days ago or less must not appear.
