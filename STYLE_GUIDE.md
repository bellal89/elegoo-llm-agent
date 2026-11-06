# Style guide

Rules for all code and text in this project: Python on the computer, C++ on the Arduino UNO and ESP32.

## Principles

Apply in this order of priority:

1. Correct.
2. Readable.
3. Simple and direct: few branches, few layers, no indirection without need.
4. Short.

Also:

- Do not duplicate code or text. Reuse the existing code.
- Do not write filler or extra explanations.

## Language

- Write all project text in English: names, comments, docstrings, docs, log messages, error messages, commit messages.
- Write all prose in ASD-STE100 Simplified Technical English: short sentences, active voice, imperative for instructions, one meaning per word.
- Use one term for one concept in names and in text. Do not use synonyms.

## Scope of changes

- Change only the code that the task needs.
- Do not reformat or restyle code outside the task.
- ELEGOO kit code (`ELEGOO Smart Robot Car Kit V4.0 */`): edit it when the task needs it. Keep the style of the file you edit.
- In project code, this guide has priority over the style of nearby code.
- Before you write a new file, read the nearest similar file. Use the same structure, if it agrees with this guide.
- Use one library for one task. Do not add an alternative library.

## Values and branches

- Use a named constant for each single value: pin, speed, angle, distance, timeout, protocol code.
- Use an enum for a finite set of related values. Do not compare with raw literals.
- Convert external input (serial, Wi-Fi, CLI, config) to enums and typed objects where it enters the program. Reject invalid input there.
- Make each branch over an enum exhaustive. Do not add a fallback branch. The checker then finds each new enum member that has no branch.

## Comments and docs

- Do not write a comment by default. Names must give the meaning.
- Write a comment only to explain why: a hardware quirk, a protocol limit, a workaround, a datasheet reference.
- If a comment explains what a block does, extract the block into a function with a clear name. Remove the comment.
- Write a docstring only for a contract that the name and types do not show: units, ranges, side effects.
- Do not write comments that repeat the code, refer to the task or describe old changes.
- Do not write file-level docstrings.

## Python

### Tooling

- Use Python 3.11 or later.
- Use `ruff` for formatting and linting.
- Use `pyright` with `reportMatchNotExhaustive`.
- Pin dependencies with `==`.

### File layout

Use this order:

1. Imports: standard library, third-party, local. Put a blank line between groups.
2. Constants.
3. `logger = logging.getLogger(__name__)`, if the module logs.
4. Exceptions.
5. Classes.
6. Functions.
7. `if __name__ == "__main__":`.

### Types

- Add type hints to all parameters and return values, also in tests.
- Write `T | None`, `list`, `dict`. Do not write `Optional`, `List`, `Dict`.
- Do not return `Any`. Return the narrowest type.
- Use `Any` only in `dict[str, Any]` for JSON data. For other `Any`, add a comment with the reason.
- Use `# type: ignore` only when no fix is possible. Add a comment with the reason.

### Enums

- Use `enum.StrEnum` for strings and `enum.IntEnum` for numeric codes.
- Do not cast enum values with `str()` or `int()`.
- Use `match` for exhaustive branches. Do not add `case _:`.

### Functions

- Use as few arguments as possible.
- Count arguments without `self` and `cls`. If there are more than two, make all arguments after the first keyword-only: `def drive(motor: Motor, *, speed: int, duration_ms: int) -> None`.
- Use a module-level function for logic without state.
- Use a class only when state persists between calls.
- Exception: put a helper that only one class uses into that class as a method.

### Classes

- Mark private members with one underscore: `_name`. Do not use `__name`.
- Use this order:
  1. `__init__`.
  2. Public fields and properties.
  3. Private fields and properties.
  4. Public methods. Dunder methods (`__enter__`, `__len__`) are public methods.
  5. Private methods.
- Keep related methods together. Do not sort by name.
- Call methods of the same class through `self` or `cls`, not through the class name.

### Dataclasses

- Use `@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)`.
- If you remove `frozen` or `kw_only`, add a comment with the reason.

### Errors

- Raise specific project exceptions.
- Do not catch an exception only to ignore it.

### Logging

- Use `%s` placeholders. Do not use f-strings in log calls.
- Use `logger.exception()` in `except` blocks.
- Use `info` for state changes, `warning` for handled problems, `error` for failures.
- Use `debug` for each message sent to or received from the car.

### Tests

- Use `pytest`. Put tests in `tests/` with the same structure as the package.
- Use test functions, not test classes.
- Use `@pytest.mark.parametrize` with `pytest.param(..., id="...")` for variants of one scenario.
- Test through the public API. Mock the serial port or socket. Do not call private members.
- Do not test the standard library or third-party libraries.
- If two tests check the same path on different levels, keep the higher-level test.
- Test failures that a manual run does not find: bad messages, timeouts, out-of-range values, reconnects.

## C++

- Use `constexpr` for constants.
- Use `enum class` for enums.
- Use `switch` without `default:` for exhaustive branches. Compile with `-Wswitch`.
