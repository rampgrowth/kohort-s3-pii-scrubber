"""Tests for kohort_sanitize helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kohort_sanitize import (
    load_client_config,
    render_tfvars,
    slug_from_prefix,
)

EXAMPLE = Path(__file__).resolve().parent / "client.yaml.example"


def test_slug_from_prefix():
    assert slug_from_prefix("kohort-datalocker/t=installs/dt=2025-09-28/") == (
        "kohort-datalocker-t=installs-dt=2025-09-28"
    )


def test_load_client_config_example():
    cfg = load_client_config(EXAMPLE)
    assert cfg.raw_bucket == "kohort-raw-data"
    assert cfg.deploy == "cloudformation"
    assert cfg.image_publish == "codebuild"
    assert cfg.manifests_prefix == "ops/manifests/"
    assert cfg.ruleset_local_path.exists()


def test_render_tfvars():
    cfg = load_client_config(EXAMPLE)
    content = render_tfvars(cfg, "123456789012.dkr.ecr.eu-west-1.amazonaws.com/kohort-s3-sanitizer:tag")
    assert "name_prefix" in content
    assert "create_batch_operations_role = true" in content
    assert "lambda_image_uri" in content


if __name__ == "__main__":
    test_slug_from_prefix()
    test_load_client_config_example()
    test_render_tfvars()
    print("ok")
