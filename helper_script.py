#!/usr/bin/env python3
"""
# ==============================================================================
# Bazel C/C++ Test Runner and Coverage Utility
#
# Script Name : bazel_helper.py
# Description : This module implements an interactive command-line utility
# for discovering, selecting, executing, and generating coverage reports for
# Bazel `cc_test` targets within a workspace.
#
# The tool is designed for local developer productivity and CI usage, providing:
# - Robust test discovery via `bazel query`
# - Interactive selection of test targets
# - Sequential test execution with detailed failure logs
# - Batch coverage execution with unified LCOV and HTML reporting
# - Deterministic exit codes suitable for automation and pipelines
#
# The implementation intentionally delegates all build and test semantics to
# Bazel, avoiding direct BUILD file parsing or workspace introspection.
#
# Usage:
#    python bazel_helper.py <directory_or_package>
#
# Example:
#    python bazel_helper.py project/
#
# Dependencies:
#   - Bazel (must be available on PATH)
#   - lcov / genhtml (required only for coverage mode)
#
# Author      : Venkades Krishnan (kvenkades7@gmail.com)
# Created     : 2025-03-10
# Last Updated: 2026-01-19
# Version     : 1.0.0
#
#
#Note:
#    This script is a developer productivity tool and does not modify Bazel
#    workspace state beyond normal test and coverage execution.
# ==============================================================================
"""

import os
import sys
import subprocess
import shutil
from typing import List, Tuple

# ==================================================
# Bazel Target Utilities
# ==================================================

# Converts user-provided filesystem paths or Bazel packages into a
# Bazel-compatible recursive target pattern. This ensures consistent
# behavior regardless of whether the input resembles a workspace path
# or a fully-qualified Bazel label.
def get_bazel_target_pattern(user_path: str) -> str:
    """
    Normalize a user-provided path into a Bazel recursive target pattern.

    Examples:
        "src/foo"        -> "//src/foo/..."
        "//src/foo"      -> "//src/foo/..."
        "//src/foo/..."  -> "//src/foo/..."

    Args:
        user_path: Path or Bazel package provided by the user.

    Returns:
        A Bazel-compatible recursive target pattern.
    """
    # Normalize path separators to avoid Windows / Unix inconsistencies
    clean_path = user_path.strip().replace("\\", "/")

    # Preserve recursive selector if already provided
    if clean_path.endswith("/..."):
        return clean_path

    # Append recursive selector to Bazel-style package
    if clean_path.startswith("//"):
        return f"{clean_path}/..."

    # Treat remaining inputs as workspace-relative paths
    return f"//{clean_path}/..."


def find_test_targets(target_pattern: str) -> List[str]:
    """
    Discover all cc_test targets under the given Bazel target pattern.

    `bazel query` is used instead of parsing BUILD files directly to
    correctly handle macros, generated targets, and Starlark logic.

    Args:
        target_pattern: Recursive Bazel target pattern.

    Returns:
        A list of fully-qualified Bazel test targets.
    """
    print(f"🔎 Discovering tests in: {target_pattern}")

    # Use `bazel query` for authoritative target discovery.
    # This avoids incorrect results caused by macros, select(), or generated rules.
    cmd = [
        "bazel", "query",
        f"kind(cc_test, {target_pattern})",
        # Continue discovering targets even if some BUILD files fail to load
        "--keep_going"
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        # Filter out empty lines from Bazel output
        return [t for t in result.stdout.splitlines() if t.strip()]

    except subprocess.CalledProcessError as e:
        print(f"❌ Bazel query failed:\n{e.stderr}")
        return []


# ==================================================
# Test Selection (Interactive)
# ==================================================

def select_tests(targets: List[str]) -> List[str]:
    """
    Interactively prompt the user to select which tests to run.

    Input options:
        - ENTER or 'all'  → run all tests
        - '3'             → run a single test
        - '1,3,5'         → run multiple tests

    The prompt repeats until valid input is provided.

    Args:
        targets: List of discovered cc_test targets.

    Returns:
        List of selected Bazel test targets.
    """
    # Interactive selection is intentionally forgiving to optimize
    # local developer iteration speed.
    print("\nAvailable tests:\n")

    for i, t in enumerate(targets, start=1):
        print(f"  {i}) {t}")

    print("\nOptions:")
    print("  ENTER or 'all'  → run ALL tests")
    print("  3              → run single test")
    print("  1,3,5          → run multiple tests")

    # Repeat until valid input is provided
    while True:
        choice = input("\nSelect test(s): ").strip().lower()

        # Default behavior: run all tests
        if choice == "" or choice == "all":
            return targets

        try:
            indices = [int(x.strip()) for x in choice.split(",")]
            selected = []

            for i in indices:
                if 1 <= i <= len(targets):
                    selected.append(targets[i - 1])
                else:
                    raise ValueError

            # Deduplicate selections while preserving order
            return list(dict.fromkeys(selected))

        except ValueError:
            print("❌ Invalid selection. Select valid test case(s) from the list.")

        print("\nValid Options:")
        print("  ENTER or 'all'  → run ALL tests")
        print("  3              → run single test")
        print("  1,3,5          → run multiple tests")


# ==================================================
# Execution Mode Selection
# ==================================================

def select_mode() -> str:
    """
    Prompt the user to choose between test execution and coverage generation.

    Returns:
        '1' for TEST MODE
        '2' for COVERAGE MODE
    """
    # Explicit separation avoids mixing test execution and coverage concerns
    print("\nSelect execution mode:")
    print("  1) TEST MODE (run tests)")
    print("  2) COVERAGE MODE (HTML report)")

    while True:
        choice = input("Enter choice [1/2]: ").strip()
        if choice in ("1", "2"):
            return choice
        print("❌ Invalid input. Please enter 1 or 2.")


# ==================================================
# Test Execution
# ==================================================

def run_tests_sequentially(targets: List[str]) -> Tuple[List[str], List[Tuple[str, str]]]:
    """
    Run tests sequentially and capture logs for failed tests.

    Sequential execution ensures deterministic output ordering and
    clear attribution of failure logs.

    Returns:
        passed_targets
        failed_targets_with_logs -> List of (target, failure_log)
    """
    passed = []
    failed = []

    print(f"\n▶ Running {len(targets)} test(s) sequentially...\n")

    # Sequential execution avoids interleaved stdout/stderr
    for idx, target in enumerate(targets, start=1):
        print(f"[{idx}/{len(targets)}] {target}")

        # Display only failing test output to keep logs concise
        cmd = [
            "bazel", "test",
            target,
            "--config=x86_64_linux",
            "--test_output=errors"
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        if result.returncode == 0:
            passed.append(target)
        else:
            failed.append((target, result.stdout))

    return passed, failed


# ==================================================
# Coverage Generation
# ==================================================

def run_batch_coverage(targets: List[str], filter_scope: str) -> bool:
    """
    Run Bazel coverage for all selected tests in a single batch.

    Batch execution improves performance and produces a unified LCOV report.

    Args:
        targets: List of Bazel test targets.
        filter_scope: Target scope used to limit instrumentation.

    Returns:
        True if coverage succeeded, False otherwise.
    """
    print(f"\n📈 Running coverage for {len(targets)} test(s)...")

    # Restrict instrumentation to project-owned targets only
    inst_filter = f"--instrumentation_filter=^{filter_scope}(/|$)"

    cmd = [
        "bazel", "coverage",
        "--config=x86_64_linux",
        "--combined_report=lcov",
        inst_filter,
        "--test_output=errors"
    ] + targets

    result = subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr)
    return result.returncode == 0


def generate_html_report() -> None:
    """
    Convert Bazel's LCOV output into a browsable HTML report using genhtml.
    """
    try:
        print("\n📊 Generating HTML coverage report...")

        # Query Bazel for the output path to remain workspace-agnostic
        bazel_out = subprocess.check_output(
            ["bazel", "info", "output_path"],
            text=True
        ).strip()

        coverage_dat = os.path.join(bazel_out, "_coverage", "_coverage_report.dat")

        if not os.path.exists(coverage_dat):
            print(f"❌ Coverage data missing at: {coverage_dat}")
            print("   (Did the tests fail to run?)")
            return

        output_dir = "genhtml"

        # Delegate HTML generation to standard LCOV tooling
        cmd = [
            "genhtml",
            coverage_dat,
            "--output", output_dir,
            "--branch-coverage",
            "--legend",
            "--highlight"
        ]

        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

        abs_path = os.path.abspath(output_dir)
        print(f"✅ Report generated: file://{abs_path}/index.html")

    except subprocess.CalledProcessError:
        print("❌ 'genhtml' failed. Ensure lcov is installed (sudo apt install lcov).")
    except FileNotFoundError:
        print("❌ 'genhtml' command not found. Please install lcov.")


# ==================================================
# Reporting
# ==================================================

def print_summary(
    passed: List[str],
    failed: List[Tuple[str, str]]
) -> None:
    """
    Print a final execution summary and manage failed-test logs.
    """
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)

    if passed:
        print(f"\nPASSED ({len(passed)}):")
        for t in passed:
            print(f" ✅ {t}")

    if failed:
        print(f"\nFAILED ({len(failed)}):")
        for target, log in failed:
            log_path = write_failed_log(target, log)
            print(f"\n ❌ {target}")
            print(f"    Log: {log_path}")
    else:
        # Remove stale failure logs when all tests pass
        cleanup_failed_logs_dir()

    if not passed and not failed:
        print("No tests were run.")

    print("\n" + "=" * 60)


def write_failed_log(target: str, log: str, base_dir: str = "logs/failed_tests") -> str:
    """
    Persist failed test output to a filesystem-safe log file.

    Returns:
        Absolute path to the written log file.
    """
    os.makedirs(base_dir, exist_ok=True)

    # Convert Bazel target label into a filesystem-safe filename
    safe_name = (
        target.replace("//", "")
              .replace("/", "_")
              .replace(":", "_")
    )

    log_path = os.path.join(base_dir, f"{safe_name}.log")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(log or "<no output captured>\n")

    return os.path.abspath(log_path)


def cleanup_failed_logs_dir(base_dir: str = "logs/failed_tests") -> None:
    """
    Remove the failed-tests log directory entirely if it exists.

    This prevents stale logs from previous runs when all tests pass.
    """
    try:
        if os.path.isdir(base_dir):
            shutil.rmtree(base_dir)
    except OSError:
        # Ignore cleanup errors to avoid masking test results
        pass


# ==================================================
# Main Entry Point
# ==================================================

if __name__ == "__main__":
    # Validate basic command-line arguments
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python bazel_helper.py <directory_path>")
        print("Example: python bazel_helper.py project/)
        sys.exit(1)

    user_path = sys.argv[1]

    # Convert user input into a Bazel target pattern
    target_pattern = get_bazel_target_pattern(user_path)

    # Discover cc_test targets under the given scope
    cc_tests = find_test_targets(target_pattern)

    if not cc_tests:
        print(f"❌ No cc_test targets found in {target_pattern}")
        sys.exit(0)

    # Interactive test selection
    selected_tests = select_tests(cc_tests)

    # Select execution mode
    mode = select_mode()

    if mode == "1":
        passed, failed = run_tests_sequentially(selected_tests)
        print_summary(passed, failed)
        sys.exit(1 if failed else 0)
    else:
        # Coverage is always executed in batch for correctness
        coverage_scope = target_pattern.replace("/...", "")
        success = run_batch_coverage(selected_tests, coverage_scope)

        if success:
            generate_html_report()
            sys.exit(0)
        else:
            print("\n❌ Coverage run failed.")
            sys.exit(1)
