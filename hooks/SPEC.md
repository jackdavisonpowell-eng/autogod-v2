# hooks/guard.py — PreToolUse hook, the only enforcement that isn't a prompt

Registered in the project's .claude/settings.json under hooks.PreToolUse (matcher "" = all
tools). Reads the hook JSON on stdin (tool_name, tool_input, cwd), prints a JSON decision
`{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",
"permissionDecisionReason":"..."}}` and exits 0 to refuse; exits 0 with no output to allow.

Allowed write roots (env AUTOGOD_ALLOWED_ROOTS, colon-separated, defaults):
  $AUTOGOD_PROJECT_DIR  (state/current/<name>/)   and   $VAULT/AUTOGOD/
Denied always, regardless of root: GATE.md, bench/tasks/**, hooks/**, loop/CLAUDE.md,
  .claude/settings.json, ~/.claude/**, ~/bin/** EXCEPT ~/bin/<name>-probe wrappers written
  by the loop's own installer (not by the model).

Rules by tool:
- Write / Edit / MultiEdit / NotebookEdit: resolve file_path (realpath, follow symlinks);
  deny unless under an allowed root and not in the deny list.
- Bash: deny if the command matches any of: `sudo`, `systemctl`, `git push`, `ssh `, `scp `,
  `rsync .*:`, `curl|wget` to a non-127.0.0.1 host, `rm -rf /`, `> /dev/sd`, `nvidia-smi -r`,
  `kill -9 -1`, `crontab`, `chmod .*[+]s`, writes via redirection (`>`/`>>`/`tee`) to a
  path outside allowed roots, `cd` to outside roots followed by a write. Also deny `python -c`
  / `bash -c` bodies containing the same tokens. Allow everything else.
- Read / Grep / Glob: allow anywhere under $HOME and $VAULT; deny ~/.ssh, ~/.claude/notify.env,
  any file named *.env, *token*, *secret*, *.pem, id_*.
- WebSearch / WebFetch: allow only when env AUTOGOD_PHASE=build; deny in look/pick.
Every deny is appended to state/guard.log (ts, tool, reason, the offending path/command).
Fail closed: any exception in the guard → deny with the exception text.
Test file hooks/test_guard.py: ≥25 cases, run with python3 -m unittest.
