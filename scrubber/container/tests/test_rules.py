"""Unit tests for rules resolution."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rules import CsvOptions, Ruleset, drop_columns_for_key, should_process  # noqa: E402


def test_drop_columns_default_and_override():
    ruleset = Ruleset(
        version="1",
        default_drop_columns=("email",),
        overrides=(("datasets/events/", ("user_id",)),),
        include_globs=(),
        exclude_globs=(),
        csv_options=CsvOptions(),
    )
    assert drop_columns_for_key(ruleset, "other/file.csv") == ("email",)
    assert drop_columns_for_key(ruleset, "datasets/events/x.csv") == (
        "email",
        "user_id",
    )


def test_include_exclude_globs():
    ruleset = Ruleset(
        version="1",
        default_drop_columns=(),
        overrides=(),
        include_globs=("*.parquet",),
        exclude_globs=("*/_temporary/*",),
        csv_options=CsvOptions(),
    )
    assert should_process(ruleset, "a/file.parquet")
    assert not should_process(ruleset, "a/file.csv")
    assert not should_process(ruleset, "a/_temporary/x.parquet")
