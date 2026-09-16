"""Unit tests for the shared run core and orchestrator loop."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import run_job  # noqa: E402
import orchestrator  # noqa: E402


class _FakePaginator:
    def __init__(self, pages):
        self._pages = pages

    def paginate(self, **kwargs):
        return iter(self._pages)


class _FakeS3:
    """Minimal S3 stub: source listing, dest listing, ruleset get, manifest put/head."""

    def __init__(self, source_keys, dest_keys=()):
        self._source_keys = list(source_keys)
        self._dest_keys = list(dest_keys)
        self.put_objects = []

    def get_paginator(self, method):
        assert method == "list_objects_v2"
        # Distinguish source vs dest listing by the Prefix passed to paginate.
        return _RoutingPaginator(self)

    def get_object(self, Bucket, Key):
        # Ruleset fetch: empty globs so defaults apply.
        return {"Body": _Body(b"{}")}

    def put_object(self, **kwargs):
        self.put_objects.append(kwargs)

    def head_object(self, Bucket, Key):
        return {"ETag": '"abc123"'}


class _RoutingPaginator:
    def __init__(self, s3):
        self._s3 = s3

    def paginate(self, Bucket, Prefix):
        # dest listing uses the dest bucket; source uses raw bucket.
        if Bucket == "dest-bucket":
            keys = self._s3._dest_keys
        else:
            keys = self._s3._source_keys
        yield {"Contents": [{"Key": k, "Size": 100} for k in keys]}


class _Body:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data


class _FakeS3Control:
    def __init__(self):
        self.jobs = []

    def create_job(self, **kwargs):
        self.jobs.append(kwargs)
        return {"JobId": "job-123"}


def _run(s3, s3control, **overrides):
    kwargs = dict(
        s3_client=s3,
        s3control_client=s3control,
        account_id="111122223333",
        raw_bucket="raw-bucket",
        source_prefix="src/",
        prefix="src/t=installs/",
        dest_bucket="dest-bucket",
        dest_prefix="sanitized/",
        ruleset_uri="s3://config/rulesets/r.json",
        config_bucket="config",
        manifests_prefix="ops/manifests/",
        batch_reports_prefix="ops/batch-reports/",
        batch_role_arn="arn:aws:iam::111122223333:role/batch",
        lambda_arn="arn:aws:lambda:eu-west-1:111122223333:function:scrubber",
        log=lambda *a, **k: None,
    )
    kwargs.update(overrides)
    return run_job.run_prefix(**kwargs)


# --- run_prefix ---

def test_run_prefix_creates_job_when_matches():
    s3 = _FakeS3(source_keys=["src/t=installs/dt=1/part-0.gz", "src/t=installs/dt=2/part-0.gz"])
    s3control = _FakeS3Control()
    result = _run(s3, s3control)
    assert result.matching_objects == 2
    assert result.job_id == "job-123"
    assert result.skipped_empty is False
    assert len(s3control.jobs) == 1
    assert len(s3.put_objects) == 1  # manifest written


def test_run_prefix_empty_is_success_no_job():
    s3 = _FakeS3(source_keys=[])
    s3control = _FakeS3Control()
    result = _run(s3, s3control, allow_empty=True)
    assert result.matching_objects == 0
    assert result.job_id is None
    assert result.skipped_empty is True
    assert s3control.jobs == []
    assert s3.put_objects == []  # no manifest written on empty


def test_run_prefix_empty_raises_when_not_allowed():
    s3 = _FakeS3(source_keys=[])
    s3control = _FakeS3Control()
    try:
        _run(s3, s3control, allow_empty=False)
    except RuntimeError as exc:
        assert "No objects matched" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when allow_empty is False and no matches")


def test_run_prefix_incremental_skips_existing():
    s3 = _FakeS3(
        source_keys=["src/t=installs/dt=1/part-0.gz", "src/t=installs/dt=2/part-0.gz"],
        dest_keys=["sanitized/t=installs/dt=1/part-0.gz"],
    )
    s3control = _FakeS3Control()
    result = _run(s3, s3control)
    assert result.matching_objects == 1  # dt=1 already sanitized, only dt=2 remains


def test_run_prefix_dry_run_creates_no_job():
    s3 = _FakeS3(source_keys=["src/t=installs/dt=1/part-0.gz"])
    s3control = _FakeS3Control()
    result = _run(s3, s3control, dry_run=True)
    assert result.matching_objects == 1
    assert result.job_id is None
    assert s3control.jobs == []
    assert s3.put_objects == []


# --- resolve_prefix ---

def test_resolve_prefix_relative_and_absolute():
    assert run_job.resolve_prefix("src/", "t=installs/") == "src/t=installs/"
    assert run_job.resolve_prefix("src/", "src/t=installs/") == "src/t=installs/"
    assert run_job.resolve_prefix("src/", "") == "src/"


def test_slug_from_prefix():
    assert run_job.slug_from_prefix("src/t=installs/dt=2025-09-28/") == "src-t=installs-dt=2025-09-28"


def test_run_prefix_concurrent_runs_use_distinct_manifest_keys():
    """Two concurrent runs over the same prefix (e.g. scheduled + manual) must not
    write to the same manifest key, or one run's in-flight Batch job ETag stops
    matching once the other overwrites the manifest."""
    s3 = _FakeS3(source_keys=["src/t=installs/dt=1/part-0.gz"])
    s3control = _FakeS3Control()
    result_a = _run(s3, s3control)
    result_b = _run(s3, s3control)
    assert result_a.manifest_uri != result_b.manifest_uri


def test_run_prefix_stable_run_scope_reuses_manifest_key():
    """A stable run_scope (e.g. an EventBridge event id) makes retries of the same
    triggering event reuse the same manifest key."""
    s3 = _FakeS3(source_keys=["src/t=installs/dt=1/part-0.gz"])
    s3control = _FakeS3Control()
    result_a = _run(s3, s3control, run_scope="event-abc")
    result_b = _run(s3, s3control, run_scope="event-abc")
    assert result_a.manifest_uri == result_b.manifest_uri


def test_create_batch_job_token_deterministic_for_same_manifest():
    """ClientRequestToken must be stable for the same manifest key+ETag so
    S3 Control can dedupe retries, but differ when the manifest changes."""
    s3 = _FakeS3(source_keys=["src/t=installs/dt=1/part-0.gz"])
    s3control = _FakeS3Control()
    _run(s3, s3control, run_scope="event-abc")
    _run(s3, s3control, run_scope="event-abc")
    tokens = [job["ClientRequestToken"] for job in s3control.jobs]
    assert tokens[0] == tokens[1]

    s3control2 = _FakeS3Control()
    _run(s3, s3control2, run_scope="event-xyz")
    assert s3control2.jobs[0]["ClientRequestToken"] != tokens[0]


# --- orchestrator ---

def test_orchestrator_loops_prefixes_and_aggregates():
    captured = []

    def fake_run_prefix(**kwargs):
        captured.append(kwargs["prefix"])
        n = 0 if kwargs["prefix"].endswith("empty/") else 3
        return run_job.RunResult(
            prefix=kwargs["prefix"],
            matching_objects=n,
            job_id=None if n == 0 else f"job-{kwargs['prefix']}",
            skipped_empty=(n == 0),
            manifest_uri=None,
        )

    orig = orchestrator.run_prefix
    orchestrator.run_prefix = fake_run_prefix

    class _Sts:
        def get_caller_identity(self):
            return {"Account": "111122223333"}

    class _Session:
        def client(self, name):
            return _Sts() if name == "sts" else object()

    orig_boto = orchestrator.boto3.Session
    orchestrator.boto3.Session = lambda *a, **k: _Session()

    env = {
        "RAW_BUCKET": "raw-bucket",
        "SOURCE_PREFIX": "src/",
        "DEST_BUCKET": "dest-bucket",
        "DEST_PREFIX": "sanitized/",
        "RULESET_URI": "s3://config/rulesets/r.json",
        "CONFIG_BUCKET": "config",
        "MANIFESTS_PREFIX": "ops/manifests/",
        "BATCH_REPORTS_PREFIX": "ops/batch-reports/",
        "BATCH_ROLE_ARN": "arn:aws:iam::111122223333:role/batch",
        "SCRUBBER_FUNCTION_ARN": "arn:aws:lambda:eu-west-1:111122223333:function:scrubber",
        "SCHEDULE_PREFIXES": '["t=installs/", "empty/"]',
    }
    old = dict(os.environ)
    os.environ.update(env)
    try:
        out = orchestrator.lambda_handler({}, None)
    finally:
        os.environ.clear()
        os.environ.update(old)
        orchestrator.run_prefix = orig
        orchestrator.boto3.Session = orig_boto

    assert captured == ["src/t=installs/", "src/empty/"]
    assert out["jobs_created"] == 1
    assert len(out["results"]) == 2


def test_parse_prefixes_json_and_csv():
    assert orchestrator._parse_prefixes('["a/", "b/"]') == ["a/", "b/"]
    assert orchestrator._parse_prefixes("a/, b/") == ["a/", "b/"]
    assert orchestrator._parse_prefixes("") == []


if __name__ == "__main__":
    test_run_prefix_creates_job_when_matches()
    test_run_prefix_empty_is_success_no_job()
    test_run_prefix_empty_raises_when_not_allowed()
    test_run_prefix_incremental_skips_existing()
    test_run_prefix_dry_run_creates_no_job()
    test_resolve_prefix_relative_and_absolute()
    test_slug_from_prefix()
    test_run_prefix_concurrent_runs_use_distinct_manifest_keys()
    test_run_prefix_stable_run_scope_reuses_manifest_key()
    test_create_batch_job_token_deterministic_for_same_manifest()
    test_orchestrator_loops_prefixes_and_aggregates()
    test_parse_prefixes_json_and_csv()
    print("ok")
