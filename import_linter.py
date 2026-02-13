#!/usr/bin/env python3

"""
Rust import organization linter.

Checks (at module level only):
1. Blank lines within a contiguous 'use' block (allowed only if a comment starts the next group)
2. 'use' statements after code (struct/enum/fn/type/trait/impl)
"""

import os
import re


def find_misplaced_rust_imports(directory):
    flagged_files = []

    # Patterns
    use_pattern = re.compile(r"^\s*(pub\s+)?use\s+")
    mod_decl_pattern = re.compile(r"^\s*(pub\s+)?mod\s+\w+;")
    const_pattern = re.compile(r"^\s*(pub(\s*\([^)]*\))?\s*)?(const|static)\s+")
    code_pattern = re.compile(
        r"^\s*(pub(\s*\([^)]*\))?\s*)?(struct|enum|type|trait|impl|fn)\s+"
    )
    attr_pattern = re.compile(r"^\s*#")
    comment_pattern = re.compile(r"^\s*//")
    macro_pattern = re.compile(r"^\s*\w+!")

    for root, dirs, files in os.walk(directory):
        # Skip dependency and git directories
        dirs[:] = [d for d in dirs if d not in ("target", ".git", ".cargo")]

        for file in files:
            if not file.endswith(".rs"):
                continue

            file_path = os.path.join(root, file)

            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    lines = f.readlines()
                except UnicodeDecodeError:
                    continue

            brace_depth = 0
            in_multiline_use = False

            # Module-level tracking state
            use_started = False  # Seen at least one 'use'
            use_finished = False  # Seen actual code after 'use'
            last_was_use = False  # Previous non-empty line was a 'use'
            last_was_comment = False  # Previous non-empty line was a comment

            for idx, line in enumerate(lines):
                line_num = idx + 1
                stripped = line.strip()

                # Handle blank lines
                if not stripped:
                    if brace_depth == 0 and use_started and not use_finished:
                        # Reset continuity flags when hitting a blank line
                        last_was_use = False
                        last_was_comment = False
                    continue

                # Handle comments (grouped imports allow blank lines if followed by a comment)
                if comment_pattern.match(stripped):
                    if brace_depth == 0:
                        last_was_comment = True
                    continue

                # Handle attributes (e.g., #[derive(...)])
                if attr_pattern.match(stripped):
                    continue

                # Handle multiline use statements (e.g., use foo::{ A, B };)
                if in_multiline_use:
                    if ";" in stripped:
                        in_multiline_use = False
                        if brace_depth == 0:
                            last_was_use = True
                    continue

                # Check for 'use' statements
                is_use = use_pattern.match(line)

                if is_use:
                    if "{" in stripped and ";" not in stripped:
                        in_multiline_use = True

                    if brace_depth == 0:
                        # Error: 'use' appears after code logic has already started
                        if use_finished:
                            flagged_files.append(
                                (file_path, f"Line {line_num}: 'use' after code.")
                            )
                            break

                        # Error: Blank line exists between imports without a descriptive comment
                        if use_started and not last_was_use and not last_was_comment:
                            flagged_files.append(
                                (
                                    file_path,
                                    f"Line {line_num}: Blank line in 'use' block without comment.",
                                )
                            )
                            break

                        use_started = True
                        last_was_use = True
                        last_was_comment = False
                    continue

                # Track brace depth to ignore scoped imports inside functions/impls
                in_string = False
                in_char = False
                open_count = 0
                close_count = 0
                prev_char = ""

                for c in stripped:
                    if c == '"' and prev_char != "\\" and not in_char:
                        in_string = not in_string
                    elif c == "'" and prev_char != "\\" and not in_string:
                        in_char = not in_char
                    elif not in_string and not in_char:
                        if c == "{":
                            open_count += 1
                        elif c == "}":
                            close_count += 1
                    prev_char = c

                old_depth = brace_depth
                brace_depth += open_count - close_count
                if brace_depth < 0:
                    brace_depth = 0

                # If we are inside a block (depth > 0), ignore import rules
                if old_depth > 0:
                    continue

                # Handle declarations that break the import section
                if (
                    mod_decl_pattern.match(line)
                    or const_pattern.match(line)
                    or macro_pattern.match(line)
                ):
                    if use_started:
                        last_was_use = False
                        last_was_comment = False
                    continue

                # Code patterns or macros mark the end of the module-level import zone
                if code_pattern.match(line):
                    use_finished = True
                    last_was_use = False
                    last_was_comment = False
                    continue

                # Any other line resets the flags
                last_was_use = False
                last_was_comment = False

    return flagged_files


if __name__ == "__main__":
    results = find_misplaced_rust_imports(".")
    if results:
        print(f"\n[!] Found {len(results)} file(s) with import issues:")
        for path, reason in results:
            print(f"  {path}: {reason}")
    else:
        print("\n[+] All imports are clean!")
