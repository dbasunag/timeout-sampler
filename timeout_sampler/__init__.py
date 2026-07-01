from __future__ import annotations

import datetime
import time
from collections.abc import Callable
from typing import Any

from simple_logger.logger import get_logger

LOGGER = get_logger(name=__name__)


def _elapsed_time_log(elapsed_time: float) -> str:
    return f"Elapsed time: {elapsed_time} [{datetime.timedelta(seconds=elapsed_time)}]"


class TimeoutExpiredError(Exception):
    def __init__(self, value: str, last_exp: Exception | None = None, elapsed_time: float | None = None) -> None:
        super().__init__()
        self.value = value
        self.last_exp = last_exp
        self.elapsed_time = elapsed_time

    def __str__(self) -> str:
        msg = f"Timed Out: {self.value}."

        if self.elapsed_time:
            msg += f"\n{_elapsed_time_log(elapsed_time=self.elapsed_time)}"

        return msg


class TimeoutSampler:
    """
    Samples the function output.

    This is a generator object that at first yields the output of callable.
    After the yield, it either raises instance of `TimeoutExpiredError` or
    sleeps `sleep` seconds.

    Yielding the output allows you to handle every value as you wish.

    exceptions_dict:
        exceptions_dict should be in the following format:
        {
            exception0: [exception0_msg0],
            exception1: [
                exception1_msg0,
                exception1_msg1
            ],
            exception2: []
        }

        If an exception is raised within `func`:
            Example exception inheritance:
                class Exception
                class AExampleError(Exception)
                class BExampleError(AExampleError)

            The raised exception's class will fall into one of three categories:
                1. An exception class specifically declared in exceptions_dict
                    exceptions_dict: {BExampleError: []}
                    raise: BExampleError
                    result: continue

                2. A child class inherited from an exception class in exceptions_dict
                    exceptions_dict: {AExampleError: []}
                    raise: BExampleError
                    result: continue

                3. Everything else, this will always re-raise the exception
                    exceptions_dict: {BExampleError: []}
                    raise: AExampleError
                    result: raise


    Args:
        wait_timeout (int): Time in seconds to wait for func to return a value equating to True
        sleep (int): Time in seconds between calls to func
        func (Callable): to be wrapped by TimeoutSampler
        exceptions_dict (dict): Exception handling definition, only exception that specifically raised in exceptions_dict will be ignored
        print_log (bool): Print elapsed time to log.
        print_func_log (bool): Add function call info to log
        print_func_args (bool): Include function arguments in log when print_func_log is True
        sensitive_keys (frozenset[str]): Additional keys to redact from logged kwargs (case-insensitive exact match).
            Merged with the default sensitive keys (authorization, token, access_token, password, secret, api_key, apikey).
            Note: "token" matches any key named exactly "token" (any case) — keys like "nextPageToken" are not affected.
    """

    _DEFAULT_SENSITIVE_KEYS: frozenset[str] = frozenset({
        "authorization",
        "token",
        "access_token",
        "password",
        "secret",
        "api_key",
        "apikey",
    })

    def __init__(
        self,
        wait_timeout: float,
        sleep: int,
        func: Callable,
        exceptions_dict: dict[type[Exception], list[str]] | None = None,
        print_log: bool = True,
        print_func_log: bool = True,
        print_func_args: bool = True,
        sensitive_keys: frozenset[str] | None = None,
        func_args: tuple[Any] | None = None,
        **func_kwargs: Any,
    ):
        self.wait_timeout = wait_timeout
        self.sleep = sleep
        self.func = func
        self.func_args = func_args or ()
        self.func_kwargs = func_kwargs or {}
        self.print_log = print_log
        self.print_func_log = print_func_log
        self.print_func_args = print_func_args
        self.sensitive_keys = (
            (self._DEFAULT_SENSITIVE_KEYS | frozenset(key.lower() for key in sensitive_keys))
            if sensitive_keys is not None
            else self._DEFAULT_SENSITIVE_KEYS
        )
        self.exceptions_dict = exceptions_dict if exceptions_dict is not None else {Exception: []}

    def _get_func_info(self, _func: Callable, type_: str) -> Any:
        # If func is partial function.
        if getattr(_func, "func", None):
            return self._get_func_info(_func=_func.func, type_=type_)  # type: ignore

        res = getattr(_func, type_, None)
        if res:
            # If func is lambda function.
            if _func.__name__ == "<lambda>":
                if type_ == "__module__":
                    return f"{res}.{_func.__qualname__.split('.')[1]}"

                elif type_ == "__name__":
                    free_vars = _func.__code__.co_freevars
                    free_vars_str = f"{'.'.join(free_vars)}." if free_vars else ""
                    return f"lambda: {free_vars_str}{'.'.join(_func.__code__.co_names)}"
            return res

    def _redact(self, data: Any) -> Any:
        """Recursively redact values whose keys exactly match sensitive keys (case-insensitive)."""
        try:
            if isinstance(data, dict):
                return {
                    key: "***" if isinstance(key, str) and key.lower() in self.sensitive_keys else self._redact(value)
                    for key, value in data.items()
                }
            if isinstance(data, list):
                return [self._redact(item) for item in data]
            if isinstance(data, tuple):
                return tuple(self._redact(item) for item in data)
        except RecursionError:
            LOGGER.warning("Redaction failed due to circular reference in data")
            return "<redaction failed: circular reference>"
        return data

    @property
    def _func_log(self) -> str:
        _func_kwargs = (
            f"Kwargs: {self._redact(self.func_kwargs)}" if (self.print_func_args and self.func_kwargs) else ""
        )
        _func_args = f"Args: {self._redact(self.func_args)}" if (self.print_func_args and self.func_args) else ""
        _func_module = self._get_func_info(_func=self.func, type_="__module__")
        _func_name = self._get_func_info(_func=self.func, type_="__name__")
        return f"Function: {_func_module}.{_func_name} {_func_args} {_func_kwargs}".strip()

    def __iter__(self) -> Any:
        """
        Call `func` and yield the result, or raise an exception on timeout.

        Yields:
            any: Return value from `func`

        Raises:
            TimeoutExpiredError: if `func` takes longer than `wait_timeout` seconds to return a value
        """
        timeout_watch = TimeoutWatch(timeout=self.wait_timeout)
        if self.print_log:
            log = (
                f"Waiting for {self.wait_timeout} seconds"
                f" [{datetime.timedelta(seconds=self.wait_timeout)}], retry every"
                f" {self.sleep} seconds."
            )

            if self.print_func_log:
                log += f" ({self._func_log})"

            LOGGER.info(log)

        last_exp = None
        elapsed_time = None
        while timeout_watch.remaining_time() > 0:
            try:
                elapsed_time = self.wait_timeout - timeout_watch.remaining_time()
                yield self.func(*self.func_args, **self.func_kwargs)
                time.sleep(self.sleep)
                elapsed_time = None

            except Exception as exp:  # noqa: BLE001
                last_exp = exp
                elapsed_time = self.wait_timeout - timeout_watch.remaining_time()

                if not self._should_ignore_exception(exp=last_exp):
                    raise TimeoutExpiredError(
                        self._get_exception_log(exp=last_exp), last_exp=last_exp, elapsed_time=elapsed_time
                    )

                time.sleep(self.sleep)
                elapsed_time = None

            finally:
                if self.print_log and elapsed_time:
                    LOGGER.info(_elapsed_time_log(elapsed_time=elapsed_time))

        raise TimeoutExpiredError(self._get_exception_log(exp=last_exp), last_exp=last_exp)

    @staticmethod
    def _is_exception_matched(exp: Exception, exception_messages: list[str]) -> bool:
        """
        Verify whether exception text is allowed and should be raised

        Args:
            exp (Exception): Exception object raised by `func`
            exception_messages (list): Either an empty list allowing all text,
                or a list of allowed strings to match against the exception text.

        Returns:
            bool: True if exception text is allowed or no exception text given, False otherwise
        """
        if not exception_messages:
            return True

        # Prevent match if provided with empty string
        return any(msg and msg in str(exp) for msg in exception_messages)

    def _should_ignore_exception(self, exp: Exception) -> bool:
        """
        Verify whether exception should be raised during execution of `func`

        Args:
            exp (Exception): Exception object raised by `func`

        Returns:
            bool: True if exp should be raised, False otherwise
        """

        for entry in self.exceptions_dict:
            if isinstance(exp, entry):  # Check inheritance for raised exception
                exception_messages = self.exceptions_dict.get(entry, [])
                if self._is_exception_matched(exp=exp, exception_messages=exception_messages):
                    return True

        return False

    def _get_exception_log(self, exp: Exception | None = None) -> str:
        """
        Get exception log message

        Args:
            exp (any): Raised exception

        Returns:
            str: Log message for exception
        """
        exp_name = exp.__class__.__name__ if exp else "N/A"
        last_exception_log = f"Last exception: {exp_name}"

        if exp:
            last_exception_log += f": {exp}"

        return f"{self.wait_timeout}\n{self._func_log if self.print_func_log else ''}\n{last_exception_log}"


class TimeoutWatch:
    """
    A time counter allowing to determine the time remaining since the start
    of a given interval
    """

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        self.start_time = time.time()

    def remaining_time(self) -> int | float:
        """
        Return the remaining part of timeout since the object was created.
        """
        _remaining_time = self.start_time + self.timeout - time.time()
        return max(0, _remaining_time)


def retry(
    wait_timeout: int,
    sleep: int,
    exceptions_dict: dict[type[Exception], list[str]] | None = None,
    print_log: bool = True,
    print_func_log: bool = True,
    print_func_args: bool = True,
    sensitive_keys: frozenset[str] | None = None,
) -> Callable:
    """
    Decorator for TimeoutSampler, For usage see TimeoutSampler.

    Args:
        wait_timeout (int): Time in seconds to wait for func to return a value equating to True
        sleep (int): Time in seconds between calls to func
        exceptions_dict (dict): Exception handling definition
        print_log (bool): Print elapsed time to log
        print_func_log (bool): Add function call info to log
        print_func_args (bool): Include function arguments in log
        sensitive_keys (frozenset[str]): Additional keys to redact from logged kwargs (case-insensitive exact match).
            Merged with the default sensitive keys.

    Example:
        from timeout_sampler import retry

        @retry(wait_timeout=1, sleep=1)
        def always_succeeds():
            return True
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args: Any, **kwargs: dict[str, Any]) -> Any:
            for sample in TimeoutSampler(
                func=func,
                wait_timeout=wait_timeout,
                sleep=sleep,
                exceptions_dict=exceptions_dict,
                print_log=print_log,
                print_func_log=print_func_log,
                print_func_args=print_func_args,
                sensitive_keys=sensitive_keys,
                func_args=args,
                **kwargs,
            ):
                if sample:
                    return sample

        return wrapper

    return decorator
