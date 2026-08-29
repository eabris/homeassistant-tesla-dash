#!/usr/bin/env python3
"""
Rename the "tesla_" entity/helper prefix used throughout this project's YAML
files (configuration.yaml, packages/tesla/*.yaml, dashboards/*.yaml,
entities-list.txt) to a different prefix — e.g. if you get a second car, or
just want a different naming scheme.

WHY A SCRIPT AND NOT A YAML VARIABLE?
Plain YAML has no string-interpolation / variables feature (no way to say
"insert this value into the middle of a string"). YAML anchors (&x / *x) only
substitute whole values/blocks, not a fragment of text inside a string. Home
Assistant also does not allow Jinja templates in `unique_id:`, `name:` (map
key), or automation `id:` fields — those are read once at config load time.
So there is no built-in way to define "tesla_" once and have it interpolated
everywhere. A one-time find/replace is the practical solution.

HOW IT DECIDES WHAT TO RENAME
This repo consistently uses lowercase `tesla_...` for machine identifiers
(entity_ids, unique_ids, automation ids, YAML keys — e.g.
`unique_id: tesla_driving_time_today_raw_v1`, `sensor.tesla_odometer`) and
capitalized `Tesla ...` for human-readable text (friendly names, comments,
brand references like "Tesla Fleet integration"). This script only replaces
the lowercase `tesla_` token pattern, so prose/brand mentions are left alone.
Use --include-labels if you *also* want capitalized "Tesla" replaced in
friendly names/comments (riskier — always review the diff before applying).

USAGE
  # Preview changes only (default, safe):
  python3 scripts/rename_tesla_prefix.py --new-prefix modely

  # Also rename human-readable "Tesla" labels (capitalized):
  python3 scripts/rename_tesla_prefix.py --new-prefix modely --include-labels

  # Apply the changes (backs up originals first):
  python3 scripts/rename_tesla_prefix.py --new-prefix modely --apply

Backups are written to .backups/rename_tesla_prefix_<timestamp>/ before any
file is modified, mirroring the original relative paths.

No third-party dependencies — uses only Python stdlib.
"""

import argparse
import difflib
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files this project uses the "tesla_" prefix in. Add more paths here if you
# add new Tesla-specific YAML/text files.
DEFAULT_TARGET_FILES = [
    "configuration.yaml",
    "entities-list.txt",
    "packages/tesla/automations.yaml",
    "packages/tesla/scripts.yaml",
    "dashboards/tesla-overview.yaml",
    "dashboards/tesla-analytics.yaml",
]


def build_patterns(old_prefix: str, new_prefix: str, include_labels: bool):
    """Return a list of (compiled_regex, replacement) pairs, applied in order."""
    patterns = []

    # Machine identifiers: lowercase "tesla_something" tokens (entity_ids,
    # unique_ids, automation ids, YAML mapping keys). Word-boundary anchored
    # so we don't accidentally match inside an unrelated longer word.
    patterns.append((
        re.compile(rf"\b{re.escape(old_prefix)}_(?=[a-z0-9_])"),
        f"{new_prefix}_",
    ))

    if include_labels:
        # Human-readable labels: capitalized "Tesla " word in friendly names /
        # markdown / comments, e.g. "Tesla Odometer" -> "Modely Odometer".
        # NOTE: this will also rewrite brand mentions like "Tesla Fleet
        # integration" or "Tesla Model X" — review the diff carefully.
        new_label = new_prefix[:1].upper() + new_prefix[1:]
        old_label = old_prefix[:1].upper() + old_prefix[1:]
        patterns.append((
            re.compile(rf"\b{re.escape(old_label)}\b"),
            new_label,
        ))

    return patterns


def rename_in_text(text: str, patterns) -> tuple[str, int]:
    total = 0
    for pattern, repl in patterns:
        text, count = pattern.subn(repl, text)
        total += count
    return text, total


def main():
    parser = argparse.ArgumentParser(
        description="Rename the tesla_ entity/helper prefix across this project's config files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--old-prefix",
        default="tesla",
        help='Current prefix to replace (default: "tesla"). Do not include the trailing underscore.',
    )
    parser.add_argument(
        "--new-prefix",
        required=True,
        help='New prefix to use instead (e.g. "modely"). Do not include the trailing underscore.',
    )
    parser.add_argument(
        "--include-labels",
        action="store_true",
        help="Also replace capitalized 'Tesla' word occurrences in friendly names/comments (riskier).",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Specific files to operate on (relative to repo root). Defaults to the known project files.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes. Without this flag, only a dry-run diff is shown.",
    )
    args = parser.parse_args()

    old_prefix = args.old_prefix.strip("_").lower()
    new_prefix = args.new_prefix.strip("_").lower()

    if not re.fullmatch(r"[a-z0-9_]+", new_prefix):
        print(f"ERROR: --new-prefix must be lowercase letters/digits/underscores only, got: {args.new_prefix!r}")
        sys.exit(1)

    target_files = args.files if args.files else DEFAULT_TARGET_FILES
    patterns = build_patterns(old_prefix, new_prefix, args.include_labels)

    changed_files = []
    total_replacements = 0

    for rel_path in target_files:
        path = REPO_ROOT / rel_path
        if not path.exists():
            print(f"SKIP (not found): {rel_path}")
            continue

        original = path.read_text(encoding="utf-8")
        updated, count = rename_in_text(original, patterns)

        if count == 0:
            print(f"No changes:       {rel_path}")
            continue

        total_replacements += count
        changed_files.append((path, rel_path, original, updated))
        print(f"Would change:     {rel_path}  ({count} replacements)")

        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
        )
        sys.stdout.writelines(diff)
        print()

    print(f"\nTotal: {total_replacements} replacements across {len(changed_files)} file(s).")

    if not changed_files:
        print("Nothing to do.")
        return

    if not args.apply:
        print("\nDry run only — no files were modified. Re-run with --apply to write changes.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = REPO_ROOT / ".backups" / f"rename_tesla_prefix_{timestamp}"

    for path, rel_path, original, updated in changed_files:
        backup_path = backup_dir / rel_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)
        path.write_text(updated, encoding="utf-8")

    print(f"\nApplied changes. Originals backed up to: {backup_dir.relative_to(REPO_ROOT)}")
    print(
        "\nNEXT STEPS:\n"
        "  1. Review the changes (git diff) before committing.\n"
        "  2. Restart Home Assistant so renamed entities/unique_ids re-register.\n"
        "  3. Old entities under the previous prefix will show as unavailable —\n"
        "     clean them up via Settings > Devices & Services > Entities, or\n"
        "     adapt scripts/cleanup_legacy_entities.py (set LEGACY_PREFIX) to remove them.\n"
    )


if __name__ == "__main__":
    main()
