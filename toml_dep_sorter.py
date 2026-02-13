#!/usr/bin/env python3

"""
Cargo.toml Dependency Block Sorter.

Features:
1. Block-level sorting: Respects groups separated by '#' comments or blank lines.
2. Multiline support: Correctly handles multi-line 'features' or dependency definitions.
3. Feature Sorting & Formatting: Automatically sorts 'features' lists.
   If 4+ features exist, expands to multi-line format.
4. Section Safety: Ensures [headers] like [dev-dependencies] never move.
5. Spacing: Automatically adds a blank line between a section's content and the next header.
6. ASCII Output: Uses terminal-friendly ASCII indicators for status messages.
"""

import os
import re


def sort_block(lines):
    """Sorts collected dependency lines and formats internal feature lists."""
    if not lines:
        return []

    units = []
    current_unit = []
    bracket_stack = 0

    for line in lines:
        current_unit.append(line)
        bracket_stack += line.count("[") - line.count("]")
        if bracket_stack <= 0 and line.strip():
            unit_str = "\n".join(current_unit)

            # Logic: Sort and format the 'features' array
            def format_features(match):
                prefix = match.group(1)  # 'features = ['
                content = match.group(2)  # content inside brackets
                suffix = match.group(3)  # ']'

                # Extract, clean, and sort items
                items = [i.strip() for i in content.split(",") if i.strip()]
                items.sort()

                if len(items) >= 4:
                    # Expand to multi-line format for 4+ items
                    formatted_items = ",\n    ".join(items)
                    return f"{prefix}\n    {formatted_items}\n{suffix}"
                else:
                    # Keep on a single line for < 4 items
                    return f"{prefix}{', '.join(items)}{suffix}"

            # Regex to find features = [...] even across multiple lines
            unit_str = re.sub(
                r"(features\s*=\s*\[)([^\]]+)(\])",
                format_features,
                unit_str,
                flags=re.DOTALL,
            )

            units.append(unit_str)
            current_unit = []

    if current_unit:
        units.append("\n".join(current_unit))

    # Sort units by dependency name (case-insensitive)
    return [
        line
        for unit in sorted(units, key=lambda x: x.strip().lower())
        for line in unit.splitlines()
    ]


def process_toml_content(content):
    """Parses TOML sections, sorts dependencies, and ensures proper spacing between sections."""
    sections = re.split(r"(\[.*dependencies.*\])", content)

    for i in range(1, len(sections), 2):
        body = sections[i + 1]

        # Check if another section (like [profile] or [workspace]) starts in the body
        next_section_match = re.search(r"\n\[", body)
        if next_section_match:
            main_body = body[: next_section_match.start()]
            tail = body[next_section_match.start() :]
        else:
            main_body = body
            tail = ""

        lines = main_body.splitlines()
        new_body = []
        current_group_lines = []
        bracket_level = 0

        for line in lines:
            stripped = line.strip()
            if bracket_level == 0 and (stripped.startswith("#") or not stripped):
                if current_group_lines:
                    new_body.extend(sort_block(current_group_lines))
                    current_group_lines = []
                new_body.append(line)
            else:
                current_group_lines.append(line)
                bracket_level += line.count("[") - line.count("]")

        if current_group_lines:
            new_body.extend(sort_block(current_group_lines))

        # Ensure proper spacing: one blank line before the next section
        formatted_body = "\n".join(new_body).rstrip()
        if tail.strip() or (i + 2 < len(sections)):
            formatted_body += "\n\n"
        else:
            formatted_body += "\n"

        sections[i + 1] = formatted_body + tail

    return "".join(sections)


def run_sorter():
    """Main execution to find and sort all Cargo.toml files."""
    root_dir = "."
    for root, dirs, files in os.walk(root_dir):
        if "target" in dirs:
            dirs.remove("target")

        for file in files:
            if file == "Cargo.toml":
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        old_content = f.read()

                    new_content = process_toml_content(old_content)

                    if old_content != new_content:
                        with open(path, "w", encoding="utf-8") as f:
                            f.write(new_content)
                        print(f"[OK] Sorted & Formatted: {path}")
                    else:
                        print(f"[-] Already sorted: {path}")
                except Exception as e:
                    print(f"[ERROR] in {path}: {e}")


if __name__ == "__main__":
    run_sorter()
