# Bazel C/C++ Test Runner and Coverage Utility

`bazel_helper.py` is an interactive command-line tool for discovering, selecting, executing, and generating coverage reports for Bazel `cc_test` targets within a workspace. It is designed for both local developer productivity and CI pipeline usage.

## Features

- **Test Discovery** — Finds all `cc_test` targets using `bazel query`
- **Interactive Selection** — Lets you choose specific targets to run
- **Sequential Execution** — Runs tests one by one with detailed failure logs
- **Coverage Reporting** — Generates unified LCOV and HTML reports via `genhtml`
- **Deterministic Exit Codes** — Suitable for automation and CI pipelines

## Requirements

- [Bazel](https://bazel.build/) — must be available on `PATH`
- `lcov` / `genhtml` — required only for coverage mode

## Usage

```bash
python bazel_helper.py <directory_or_package>
