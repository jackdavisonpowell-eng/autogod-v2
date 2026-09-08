"""judge/test_judge.py — >=8 cases for judge/judge.py. Run:
python3 -m unittest judge.test_judge
"""
import datetime
import importlib.util
import os
import tempfile
import unittest

# Load judge/judge.py by path under a distinct module name: `import judge`
# here would collide with the `judge` *package* (this directory) that
# `python3 -m unittest judge.test_judge` already put in sys.modules.
_JUDGE_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "judge.py")
_spec = importlib.util.spec_from_file_location("_judge_impl", _JUDGE_PY)
judge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(judge)


def make_project(state_dir, name, milestone_at, probe_kind, target, keep_if, shape="a shape"):
    project_dir = os.path.join(state_dir, "current", name)
    os.makedirs(project_dir, exist_ok=True)
    with open(os.path.join(project_dir, "PROJECT.md"), "w") as f:
        f.write(
            "# %s\n\nevidence: \"x\"\nsentence: \"y\"\noutside: \"z\"\n"
            "probe:\n  kind: %s\n  target: \"%s\"\n  keep_if: \"%s\"\n"
            "milestone_at: %s\ndecided:\nnext: \"do it\"\nlog:\n"
            % (name, probe_kind, target, keep_if, milestone_at)
        )
    with open(os.path.join(project_dir, "judge.yaml"), "w") as f:
        f.write(
            'name: "%s"\nshape: "%s"\nprobe:\n  kind: %s\n  target: "%s"\n  keep_if: "%s"\n'
            % (name, shape, probe_kind, target, keep_if)
        )
    return project_dir


class JudgeTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "state")
        self.vault = os.path.join(self.tmp.name, "vault")
        os.makedirs(os.path.join(self.state, "current"), exist_ok=True)
        os.makedirs(os.path.join(self.vault, "AUTOGOD"), exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()


class TestParseKeepIf(unittest.TestCase):
    def test_ge_form(self):
        self.assertEqual(judge.parse_keep_if(">=3"), (">=", 3))

    def test_ge_descriptive_form(self):
        self.assertEqual(judge.parse_keep_if(">=3 runs in 7 days"), (">=", 3))

    def test_gt_form(self):
        self.assertEqual(judge.parse_keep_if(">0"), (">", 0))

    def test_mtime_form(self):
        self.assertEqual(judge.parse_keep_if("mtime"), ("mtime", None))

    def test_any_form(self):
        self.assertEqual(judge.parse_keep_if("any"), (">=", 1))

    def test_evaluate_ge(self):
        self.assertTrue(judge.evaluate_keep(">=", 3, 3))
        self.assertFalse(judge.evaluate_keep(">=", 3, 2))

    def test_evaluate_gt(self):
        self.assertTrue(judge.evaluate_keep(">", 0, 1))
        self.assertFalse(judge.evaluate_keep(">", 0, 0))

    def test_evaluate_mtime(self):
        self.assertTrue(judge.evaluate_keep("mtime", None, 1))
        self.assertFalse(judge.evaluate_keep("mtime", None, 0))


class TestExecProbe(JudgeTestBase):
    def test_keep_exec_probe_above_threshold(self):
        milestone = datetime.date(2026, 8, 25)
        pdir = make_project(self.state, "proj-a", milestone.isoformat(), "exec", "proj-a", ">=2")
        usage = os.path.join(self.state, "usage.log")
        with open(usage, "w") as f:
            f.write("2026-08-26T08:00:00 proj-a\n")
            f.write("2026-08-27T08:00:00 proj-a\n")
            f.write("2026-08-27T08:00:00 other-proj\n")  # different target, ignored
            f.write("2026-09-05T08:00:00 proj-a\n")  # outside the 7-day window, ignored

        today = datetime.date(2026, 9, 1)  # milestone + 7 days
        verdict = judge.judge_project(pdir, self.state, self.vault, today, dry_run=False)
        self.assertEqual(verdict["status"], "keep")
        self.assertEqual(verdict["measured"], 2)
        self.assertFalse(os.path.exists(pdir))
        self.assertTrue(os.path.isdir(os.path.join(self.state, "kept", "proj-a")))
        with open(os.path.join(self.state, "kept.md")) as f:
            self.assertIn("proj-a", f.read())

    def test_kill_exec_probe_below_threshold(self):
        milestone = datetime.date(2026, 8, 25)
        pdir = make_project(self.state, "proj-b", milestone.isoformat(), "exec", "proj-b", ">=3")
        usage = os.path.join(self.state, "usage.log")
        with open(usage, "w") as f:
            f.write("2026-08-26T08:00:00 proj-b\n")

        today = datetime.date(2026, 9, 1)
        verdict = judge.judge_project(pdir, self.state, self.vault, today, dry_run=False)
        self.assertEqual(verdict["status"], "kill")
        self.assertFalse(os.path.exists(pdir))
        with open(os.path.join(self.state, "dead.md")) as f:
            content = f.read()
        self.assertIn("proj-b", content)
        self.assertIn("exec", content)

    def test_dry_run_does_not_touch_disk(self):
        milestone = datetime.date(2026, 8, 25)
        pdir = make_project(self.state, "proj-c", milestone.isoformat(), "exec", "proj-c", ">=100")
        today = datetime.date(2026, 9, 1)
        verdict = judge.judge_project(pdir, self.state, self.vault, today, dry_run=True)
        self.assertEqual(verdict["status"], "kill")
        self.assertTrue(os.path.exists(pdir))  # untouched
        self.assertFalse(os.path.exists(os.path.join(self.state, "dead.md")))


class TestWaitingAndSkip(JudgeTestBase):
    def test_waiting_before_day_seven(self):
        milestone = datetime.date(2026, 8, 25)
        pdir = make_project(self.state, "proj-d", milestone.isoformat(), "exec", "proj-d", ">=1")
        today = datetime.date(2026, 8, 30)  # only 5 days in
        verdict = judge.judge_project(pdir, self.state, self.vault, today, dry_run=False)
        self.assertEqual(verdict["status"], "waiting")
        self.assertTrue(os.path.exists(pdir))

    def test_waiting_when_milestone_not_set(self):
        pdir = make_project(self.state, "proj-e", "", "exec", "proj-e", ">=1")
        today = datetime.date(2026, 9, 1)
        verdict = judge.judge_project(pdir, self.state, self.vault, today, dry_run=False)
        self.assertEqual(verdict["status"], "waiting")
        self.assertTrue(os.path.exists(pdir))

    def test_skip_on_unknown_probe_kind(self):
        milestone = datetime.date(2026, 8, 25)
        pdir = make_project(self.state, "proj-f", milestone.isoformat(), "carrier-pigeon", "x", ">=1")
        today = datetime.date(2026, 9, 1)
        verdict = judge.judge_project(pdir, self.state, self.vault, today, dry_run=False)
        self.assertEqual(verdict["status"], "skip")
        self.assertTrue(os.path.exists(pdir))

    def test_skip_on_missing_judge_yaml(self):
        pdir = os.path.join(self.state, "current", "proj-g")
        os.makedirs(pdir)
        with open(os.path.join(pdir, "PROJECT.md"), "w") as f:
            f.write("milestone_at: 2026-08-25\n")
        today = datetime.date(2026, 9, 1)
        verdict = judge.judge_project(pdir, self.state, self.vault, today, dry_run=False)
        self.assertEqual(verdict["status"], "skip")


class TestHttpProbe(JudgeTestBase):
    def test_keep_http_probe(self):
        milestone = datetime.date(2026, 8, 25)
        log_path = os.path.join(self.tmp.name, "access.log")
        with open(log_path, "w") as f:
            f.write("2026-08-26T09:00:00 GET /\n")
            f.write("2026-08-27T09:00:00 GET /\n")
            f.write("2026-09-10T09:00:00 GET /\n")  # outside window
        pdir = make_project(
            self.state, "proj-h", milestone.isoformat(), "http", log_path, ">=2"
        )
        today = datetime.date(2026, 9, 1)
        verdict = judge.judge_project(pdir, self.state, self.vault, today, dry_run=False)
        self.assertEqual(verdict["status"], "keep")
        self.assertEqual(verdict["measured"], 2)


class TestLinkProbe(JudgeTestBase):
    def test_keep_link_probe_finds_backlink(self):
        milestone = datetime.date(2026, 8, 25)
        note_dir = os.path.join(self.vault, "Journal")
        os.makedirs(note_dir, exist_ok=True)
        note_path = os.path.join(note_dir, "2026-08-26.md")
        with open(note_path, "w") as f:
            f.write("today I used [[proj-i]] again, nice\n")
        in_window = datetime.datetime(2026, 8, 26, 12, 0, 0).timestamp()
        os.utime(note_path, (in_window, in_window))

        pdir = make_project(self.state, "proj-i", milestone.isoformat(), "link", "proj-i", ">=1")
        today = datetime.date(2026, 9, 1)
        verdict = judge.judge_project(pdir, self.state, self.vault, today, dry_run=False)
        self.assertEqual(verdict["status"], "keep")
        self.assertGreaterEqual(verdict["measured"], 1)

    def test_link_probe_ignores_autogod_subtree(self):
        milestone = datetime.date(2026, 8, 25)
        auto_path = os.path.join(self.vault, "AUTOGOD", "note.md")
        with open(auto_path, "w") as f:
            f.write("[[proj-j]] mentioned only here, inside AUTOGOD\n")
        in_window = datetime.datetime(2026, 8, 26, 12, 0, 0).timestamp()
        os.utime(auto_path, (in_window, in_window))

        pdir = make_project(self.state, "proj-j", milestone.isoformat(), "link", "proj-j", ">=1")
        today = datetime.date(2026, 9, 1)
        verdict = judge.judge_project(pdir, self.state, self.vault, today, dry_run=False)
        self.assertEqual(verdict["status"], "kill")
        self.assertEqual(verdict["measured"], 0)


class TestFileProbe(JudgeTestBase):
    def test_keep_file_probe_modified_in_window(self):
        milestone = datetime.date(2026, 8, 25)
        target = os.path.join(self.tmp.name, "some_file.txt")
        with open(target, "w") as f:
            f.write("x")
        in_window = datetime.datetime(2026, 8, 28, 0, 0, 0).timestamp()
        os.utime(target, (in_window, in_window))

        pdir = make_project(self.state, "proj-k", milestone.isoformat(), "file", target, "mtime")
        today = datetime.date(2026, 9, 1)
        verdict = judge.judge_project(pdir, self.state, self.vault, today, dry_run=False)
        self.assertEqual(verdict["status"], "keep")

    def test_kill_file_probe_not_modified(self):
        milestone = datetime.date(2026, 8, 25)
        target = os.path.join(self.tmp.name, "stale_file.txt")
        with open(target, "w") as f:
            f.write("x")
        before_window = datetime.datetime(2026, 8, 1, 0, 0, 0).timestamp()
        os.utime(target, (before_window, before_window))

        pdir = make_project(self.state, "proj-l", milestone.isoformat(), "file", target, "mtime")
        today = datetime.date(2026, 9, 1)
        verdict = judge.judge_project(pdir, self.state, self.vault, today, dry_run=False)
        self.assertEqual(verdict["status"], "kill")


if __name__ == "__main__":
    unittest.main()
