"""loop/test_pick.py — pick.py's --dry-run mode (build-order step 2:
LOOK + gate, no build). Run: python3 -m unittest loop.test_pick
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pick  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = "2026-01-15"


class PickTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "state")
        os.makedirs(os.path.join(self.state, "candidates"), exist_ok=True)
        os.makedirs(os.path.join(self.state, "current"), exist_ok=True)
        with open(os.path.join(self.state, "candidates", "%s.md" % TODAY), "w") as f:
            f.write(
                '# candidates — %s\n\n- quote: "I wish there was a tire pressure check"\n'
                "  source: Journal/x.md:3\n  date: %s\n" % (TODAY, TODAY)
            )

        self._old_environ = dict(os.environ)
        os.environ["AUTOGOD_TODAY"] = TODAY
        os.environ.pop("AUTOGOD_MOCK_PICK_FIXTURE", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old_environ)
        self.tmp.cleanup()

    def cand_content(self):
        with open(os.path.join(self.state, "candidates", "%s.md" % TODAY)) as f:
            return f.read()

    def current_dirs(self):
        cur = os.path.join(self.state, "current")
        return [d for d in os.listdir(cur) if os.path.isdir(os.path.join(cur, d))]


class TestDryRunValidPick(PickTestBase):
    def test_no_project_created(self):
        os.environ["AUTOGOD_MOCK_PICK_FIXTURE"] = "pick_response.txt"
        rc = pick.main(
            ["--state", self.state, "--root", ROOT, "--driver", "mock", "--dry-run"]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(self.current_dirs(), [])

    def test_gate_verdict_appended_with_name_and_yaml(self):
        os.environ["AUTOGOD_MOCK_PICK_FIXTURE"] = "pick_response.txt"
        pick.main(["--state", self.state, "--root", ROOT, "--driver", "mock", "--dry-run"])
        content = self.cand_content()
        self.assertIn("## Gate verdict", content)
        self.assertIn("would have picked: tire-pressure-check", content)
        self.assertIn("```yaml", content)
        self.assertIn("name: tire-pressure-check", content)
        self.assertIn("---PLAN---", content)


class TestDryRunNone(PickTestBase):
    def test_no_project_created_on_none(self):
        os.environ["AUTOGOD_MOCK_PICK_FIXTURE"] = "pick_response_none.txt"
        rc = pick.main(
            ["--state", self.state, "--root", ROOT, "--driver", "mock", "--dry-run"]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(self.current_dirs(), [])

    def test_gate_verdict_shows_none(self):
        os.environ["AUTOGOD_MOCK_PICK_FIXTURE"] = "pick_response_none.txt"
        pick.main(["--state", self.state, "--root", ROOT, "--driver", "mock", "--dry-run"])
        content = self.cand_content()
        self.assertIn("## Gate verdict", content)
        self.assertIn("would have picked: NONE", content)
        self.assertIn("NONE:", content)


class TestDryRunDeadShapeMatch(PickTestBase):
    def test_refused_and_no_project_created(self):
        with open(os.path.join(self.state, "dead.md"), "w") as f:
            f.write("# dead\n")
            f.write(
                "2026-01-01 | old-tire-thing | warns when a sensor value crosses a "
                "threshold by reading a local log | exec | killed, no runs\n"
            )
        os.environ["AUTOGOD_MOCK_PICK_FIXTURE"] = "pick_response_dead_shape_match.txt"
        rc = pick.main(
            ["--state", self.state, "--root", ROOT, "--driver", "mock", "--dry-run"]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(self.current_dirs(), [])

    def test_gate_verdict_names_the_matched_dead_line(self):
        with open(os.path.join(self.state, "dead.md"), "w") as f:
            f.write("# dead\n")
            f.write(
                "2026-01-01 | old-tire-thing | warns when a sensor value crosses a "
                "threshold by reading a local log | exec | killed, no runs\n"
            )
        os.environ["AUTOGOD_MOCK_PICK_FIXTURE"] = "pick_response_dead_shape_match.txt"
        pick.main(["--state", self.state, "--root", ROOT, "--driver", "mock", "--dry-run"])
        content = self.cand_content()
        self.assertIn("would have picked: NONE", content)
        self.assertIn("refused:", content)
        self.assertIn("shape fuzzy-matches dead.md line:", content)
        self.assertIn("old-tire-thing", content)  # the matched dead line itself, verbatim


class TestNonDryRunUnaffected(PickTestBase):
    def test_still_creates_project_and_does_not_touch_candidates_file(self):
        os.environ["AUTOGOD_MOCK_PICK_FIXTURE"] = "pick_response.txt"
        before = self.cand_content()
        rc = pick.main(["--state", self.state, "--root", ROOT, "--driver", "mock"])
        self.assertEqual(rc, 0)
        self.assertIn("tire-pressure-check", self.current_dirs())
        after = self.cand_content()
        self.assertEqual(before, after)  # no Gate verdict section in normal mode


class TestValidateReportsMatchedDeadLine(unittest.TestCase):
    def test_validate_reason_includes_dead_line(self):
        dead_line = "2026-01-01 | old-thing | some shape about local sensor logs | exec | dead"
        dead_shapes = [("some shape about local sensor logs", dead_line)]
        data = {
            "name": "new-thing",
            "evidence": "e",
            "sentence": "s",
            "outside": "o",
            "probe": {"kind": "exec", "target": "t", "keep_if": ">=1"},
            "milestone": "m",
            "shape": "some shape about local sensor logs, reworded a bit",
        }
        why = pick.validate(data, dead_shapes)
        self.assertIsNotNone(why)
        self.assertIn(dead_line, why)


if __name__ == "__main__":
    unittest.main()
