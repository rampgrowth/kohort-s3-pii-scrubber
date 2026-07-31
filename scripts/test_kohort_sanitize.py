"""Tests for kohort_sanitize helpers."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

from kohort_sanitize import (
    load_client_config,
    render_tfvars,
    resolve_run_prefix,
    slug_from_prefix,
)

EXAMPLE = Path(__file__).resolve().parent / "client.yaml.example"


def _config_from(**overrides):
    """Load client.yaml.example with overrides applied; None removes a key."""
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    for key, value in overrides.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "client.yaml"
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        return load_client_config(path)


def test_slug_from_prefix():
    assert slug_from_prefix("kohort-datalocker/t=installs/dt=2025-09-28/") == (
        "kohort-datalocker-t=installs-dt=2025-09-28"
    )


def test_load_client_config_example():
    cfg = load_client_config(EXAMPLE)
    assert cfg.raw_bucket == "your-company-raw-data"
    assert cfg.deploy == "cloudformation"
    assert cfg.image_publish == "codebuild"
    assert cfg.manifests_prefix == "ops/manifests/"
    assert cfg.ruleset_local_path.exists()
    assert cfg.aws_profile is None
    assert cfg.image_tag == cfg.public_image.rsplit(":", 1)[-1]


def test_resolve_run_prefix():
    cfg = load_client_config(EXAMPLE)  # source_prefix: appsflyer-datalocker/
    src = cfg.source_prefix
    assert resolve_run_prefix(cfg, "t=installs/dt=2025-09-28/") == f"{src}t=installs/dt=2025-09-28/"
    assert resolve_run_prefix(cfg, f"{src}t=installs/") == f"{src}t=installs/"
    assert resolve_run_prefix(cfg, src) == src
    assert resolve_run_prefix(cfg, src.rstrip("/")) == src
    assert resolve_run_prefix(cfg, "") == src


def test_render_tfvars():
    cfg = load_client_config(EXAMPLE)
    content = render_tfvars(cfg, "123456789012.dkr.ecr.eu-west-1.amazonaws.com/kohort-s3-sanitizer:tag")
    assert "name_prefix" in content
    assert "create_batch_operations_role = true" in content
    assert "lambda_image_uri" in content
    assert f'dest_bucket_name   = "{cfg.dest_bucket}"' in content
    # The driver creates the sanitized bucket, so IaC must not own it.
    assert "create_dest_bucket = false" in content


def test_separate_dest_bucket():
    cfg = _config_from(dest_bucket="your-company-sanitized")
    assert cfg.dest_bucket == "your-company-sanitized"
    assert cfg.dest_bucket != cfg.raw_bucket
    assert cfg.create_dest_bucket is True


def test_dest_bucket_defaults_to_raw_bucket():
    cfg = _config_from(dest_bucket=None, dest_prefix=None)
    assert cfg.dest_bucket == cfg.raw_bucket
    assert cfg.create_dest_bucket is False
    assert cfg.dest_prefix == f"sanitized/{cfg.source_prefix}"


def test_dest_prefix_defaults_to_sanitized_regardless_of_dest_bucket():
    same_bucket = _config_from(dest_bucket=None, dest_prefix=None)
    separate_bucket = _config_from(dest_bucket="your-company-sanitized", dest_prefix=None)
    assert same_bucket.dest_prefix == f"sanitized/{same_bucket.source_prefix}"
    assert separate_bucket.dest_prefix == f"sanitized/{separate_bucket.source_prefix}"


def test_dest_prefix_override():
    cfg = _config_from(dest_bucket="your-company-sanitized", dest_prefix="custom/")
    assert cfg.dest_prefix == "custom/"


def test_empty_dest_prefix_allowed_for_separate_bucket():
    cfg = _config_from(dest_bucket="your-company-sanitized", dest_prefix="")
    assert cfg.dest_prefix == ""


def test_same_bucket_requires_dest_prefix():
    try:
        _config_from(dest_bucket=None, dest_prefix="")
    except ValueError as exc:
        assert "dest_prefix is required" in str(exc)
    else:
        raise AssertionError("expected ValueError when dest_prefix is empty on the raw bucket")


def test_create_dest_bucket_can_be_disabled():
    cfg = _config_from(dest_bucket="your-company-sanitized", create_dest_bucket=False)
    assert cfg.create_dest_bucket is False


if __name__ == "__main__":
    test_slug_from_prefix()
    test_load_client_config_example()
    test_resolve_run_prefix()
    test_render_tfvars()
    test_separate_dest_bucket()
    test_dest_bucket_defaults_to_raw_bucket()
    test_dest_prefix_defaults_to_sanitized_regardless_of_dest_bucket()
    test_dest_prefix_override()
    test_empty_dest_prefix_allowed_for_separate_bucket()
    test_same_bucket_requires_dest_prefix()
    test_create_dest_bucket_can_be_disabled()
    print("ok")
