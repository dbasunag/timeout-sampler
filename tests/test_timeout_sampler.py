import re

import pytest

from timeout_sampler import TimeoutExpiredError, TimeoutSampler, retry


class TestTimeoutSampler:
    @staticmethod
    def _raise_exception(runtime_exception):
        if runtime_exception:
            raise runtime_exception

    def _trigger_func_exception_during_iter(self, exceptions_dict, runtime_exception):
        for _ in TimeoutSampler(
            wait_timeout=1,
            sleep=1,
            func=self._raise_exception,
            exceptions_dict=exceptions_dict,
            print_log=False,
            runtime_exception=runtime_exception,
        ):
            continue

    @pytest.mark.parametrize(
        "test_params",
        [
            pytest.param(
                {
                    "init_exceptions_dict": {
                        KeyError: [],
                    },
                    "runtime_exception": ValueError(),
                },
                id="init_keyerror_raise_valueerror_with_no_msg",
            ),
            pytest.param(
                {
                    "init_exceptions_dict": {},
                    "runtime_exception": ValueError(),
                },
                id="init_any_exception_raise_valueerror_with_no_msg",
            ),
            pytest.param(
                {
                    "init_exceptions_dict": {
                        ValueError: ["allowed exception text"],
                    },
                    "runtime_exception": ValueError("test"),
                },
                id="init_valueerror_with_msg_raise_valueerror_with_invalid_msg",
            ),
            pytest.param(
                {
                    "init_exceptions_dict": {
                        KeyError: ["allowed exception text"],
                        IndexError: ["allowed exception text"],
                        ValueError: ["allowed exception text"],
                    },
                    "runtime_exception": IndexError("test"),
                },
                id="init_multi_exceptions_raise_allowed_with_invalid_msg",
            ),
        ],
    )
    def test_timeout_sampler_raises(self, test_params):
        with pytest.raises(TimeoutExpiredError):
            self._trigger_func_exception_during_iter(
                exceptions_dict=test_params.get("init_exceptions_dict"),
                runtime_exception=test_params.get("runtime_exception"),
            )

    @pytest.mark.parametrize(
        "test_params, expected",
        [
            pytest.param(
                {},
                {
                    "exception_log_regex": "^.*\nLast exception: N/A",
                },
                id="noargs_timeout_only",
            ),
            pytest.param(
                {
                    "runtime_exception": Exception(),
                },
                {
                    "exception_log_regex": "^.*\nLast exception: Exception:",
                },
                id="noargs_raise_exception_with_no_msg",
            ),
            pytest.param(
                {
                    "runtime_exception": ValueError(),
                },
                {
                    "exception_log_regex": "^.*\nLast exception: ValueError:",
                },
                id="noargs_raise_valueerror_with_no_msg",
            ),
            pytest.param(
                {
                    "init_exceptions_dict": {
                        ValueError: ["test"],
                    },
                    "runtime_exception": ValueError("test"),
                },
                {
                    "exception_log_regex": "^.*\nLast exception: ValueError: test",
                },
                id="init_valueerror_with_msg_raise_valueerror_with_allowed_msg",
            ),
            pytest.param(
                {
                    "init_exceptions_dict": {
                        KeyError: ["allowed exception text"],
                        IndexError: ["allowed exception text"],
                        ValueError: ["allowed exception text"],
                    },
                    "runtime_exception": IndexError("my allowed exception text"),
                },
                {
                    "exception_log_regex": ("^.*\nLast exception: IndexError: my allowed exception text"),
                },
                id="init_multi_exceptions_raise_allowed_with_allowed_msg",
            ),
        ],
    )
    def test_timeout_sampler_raises_timeout(self, test_params, expected):
        exception_match = None
        exception_log = None
        try:
            self._trigger_func_exception_during_iter(
                exceptions_dict=test_params.get("init_exceptions_dict"),
                runtime_exception=test_params.get("runtime_exception"),
            )
        except TimeoutExpiredError as exp:
            exception_log = str(exp)
            exception_match = re.compile(pattern=expected["exception_log_regex"], flags=re.DOTALL).match(
                string=exception_log
            )

        assert exception_match, f"Expected Regex: {expected['exception_log_regex']!r} Exception Log: {exception_log!r}"


def test_sampler():
    sampler = TimeoutSampler(wait_timeout=1, sleep=1, print_log=False, func=lambda: True)
    for sample in sampler:
        if sample:
            return

    pytest.fail("Sampler rise timeout")


def test_sampler_negative():
    sampler = TimeoutSampler(
        wait_timeout=10,
        sleep=1,
        func=lambda: False,
        print_log=False,
    )
    with pytest.raises(TimeoutExpiredError):
        for sample in sampler:
            if sample:
                return


# retry decorator tests


@retry(
    wait_timeout=1,
    sleep=1,
    print_log=False,
)
def always_succeeds():
    return True


@retry(
    wait_timeout=1,
    sleep=1,
    print_log=False,
)
def never_succeeds():
    return False


def test_decorator():
    always_succeeds()


def test_decorator_negative():
    with pytest.raises(TimeoutExpiredError):
        never_succeeds()


class TestSensitiveKeyRedaction:
    @pytest.mark.parametrize(
        "sampler_kwargs, must_not_contain, must_contain",
        [
            pytest.param(
                {"headers": {"Authorization": "Bearer secret-token", "Content-Type": "application/json"}},
                ["secret-token"],
                ["***", "application/json"],
                id="test_default_authorization_redacted",
            ),
            pytest.param(
                {"config": {"api_key": "my-api-key", "timeout": 30}},  # pragma: allowlist secret
                ["my-api-key"],
                ["***", "30"],
                id="test_nested_api_key_redacted",
            ),
            pytest.param(
                {"data": {"password": "hunter2", "username": "admin"}},  # pragma: allowlist secret
                ["hunter2"],
                ["***", "admin"],
                id="test_password_redacted",
            ),
            pytest.param(
                {
                    "sensitive_keys": frozenset({"my_secret_field"}),
                    "my_secret_field": "top-secret",  # pragma: allowlist secret
                    "safe_field": "visible",
                },
                ["top-secret"],
                ["visible"],
                id="test_custom_sensitive_keys",
            ),
            pytest.param(
                {
                    "sensitive_keys": frozenset({"x-custom-secret"}),
                    "headers": {
                        "Authorization": "Bearer default-secret",  # pragma: allowlist secret
                        "x-custom-secret": "custom-value",  # pragma: allowlist secret
                    },
                },
                ["default-secret", "custom-value"],
                ["***"],
                id="test_custom_keys_merged_with_defaults",
            ),
            pytest.param(
                {"args_list": [{"token": "secret-in-list"}]},  # pragma: allowlist secret
                ["secret-in-list"],
                ["***"],
                id="test_sensitive_key_in_list_of_dicts",
            ),
            pytest.param(
                {
                    "sensitive_keys": frozenset(),
                    "headers": {"Authorization": "Bearer still-redacted"},
                },
                ["still-redacted"],
                ["***"],
                id="test_empty_sensitive_keys_still_uses_defaults",
            ),
            pytest.param(
                {
                    "print_func_args": False,
                    "headers": {"Authorization": "Bearer secret"},
                },
                ["secret", "Kwargs"],
                [],
                id="test_print_func_args_false_hides_everything",
            ),
            pytest.param(
                {"pagination": {"nextPageToken": "abc123", "token_count": 42, "Authorization": "Bearer redact-me"}},
                ["redact-me"],
                ["abc123", "42", "nextPageToken", "token_count"],
                id="test_similar_named_keys_not_redacted",
            ),
            pytest.param(
                {"headers": {"AUTHORIZATION": "Bearer upper-secret", "Content-Type": "text/plain"}},
                ["upper-secret"],
                ["***", "text/plain"],
                id="test_uppercase_key_redacted",
            ),
            pytest.param(
                {
                    "sensitive_keys": frozenset({"X-My-Token"}),
                    "headers": {"X-My-Token": "custom-upper"},  # pragma: allowlist secret
                },
                ["custom-upper"],
                ["***"],
                id="test_custom_key_case_insensitive",
            ),
        ],
    )
    def test_sensitive_key_redaction(self, sampler_kwargs, must_not_contain, must_contain):
        """Sensitive kwargs should be redacted from log output based on configuration."""
        sampler = TimeoutSampler(wait_timeout=1, sleep=1, func=lambda: True, print_log=False, **sampler_kwargs)
        log_output = sampler._func_log
        for value in must_not_contain:
            assert value not in log_output, f"Value {value!r} should not appear in log"
        for value in must_contain:
            assert value in log_output, f"Value {value!r} should appear in log"

    def test_positional_args_redacted(self):
        """Sensitive keys in dicts passed as positional args should be redacted."""
        sampler = TimeoutSampler(
            wait_timeout=1,
            sleep=1,
            func=lambda *args: True,
            print_log=False,
            func_args=({"Authorization": "Bearer pos-secret", "safe": "visible"},),  # pragma: allowlist secret
        )
        log_output = sampler._func_log
        assert "pos-secret" not in log_output, "Positional arg secret should be redacted"
        assert "visible" in log_output, "Non-sensitive positional arg should be visible"
        assert "***" in log_output, "Redacted placeholder should appear"

    def test_non_string_dict_keys_not_crash(self):
        """Dicts with non-string keys (int, tuple) should not crash _redact."""
        sampler = TimeoutSampler(
            wait_timeout=1,
            sleep=1,
            func=lambda: True,
            print_log=False,
            data={1: "int-key-value", (2, 3): "tuple-key-value", "password": "secret123"},  # pragma: allowlist secret
        )
        log_output = sampler._func_log
        assert "int-key-value" in log_output, "Non-string key value should be visible"
        assert "tuple-key-value" in log_output, "Tuple key value should be visible"
        assert "secret123" not in log_output, "String sensitive key should still be redacted"
        assert "***" in log_output, "Redacted placeholder should appear"
