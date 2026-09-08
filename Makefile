PY := python3

.PHONY: test pass-mock

test:
	$(PY) -m unittest hooks.test_guard judge.test_judge loop.test_pick -v

pass-mock:
	bash loop/pass_mock_test.sh
