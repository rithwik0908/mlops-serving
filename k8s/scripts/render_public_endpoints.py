#!/usr/bin/env python3
"""Render public nip.io hostnames from a single base host."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

PUBLIC_HOST_FILES = (
    "k8s/platform/minio/deployment.yaml",
    "k8s/platform/minio/ingress-api.yaml",
    "k8s/platform/minio/ingress-console.yaml",
    "k8s/platform/mlflow/ingress.yaml",
    "k8s/platform/observability/deployment-grafana.yaml",
    "k8s/platform/observability/ingress-grafana.yaml",
    "k8s/platform/observability/ingress-prometheus.yaml",
    "k8s/integration/ingress-zulip-bridge.yaml",
    "k8s/inference/ingress/tiered-ingress.yaml",
    "k8s/zulip/values-chameleon.yaml",
)

PLACEHOLDER = "FLOATING_IP_PLACEHOLDER"
NIP_HOST_PATTERN = re.compile(
    r"(?P<prefix>[a-z0-9-]+\.)"
    r"(?P<host>(?:\d{1,3}(?:\.\d{1,3}){3}\.nip\.io)|(?:FLOATING_IP_PLACEHOLDER\.nip\.io))"
)


def render_file(path: Path, public_nip_base: str) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = original.replace(f"{PLACEHOLDER}.nip.io", public_nip_base)
    updated = NIP_HOST_PATTERN.sub(rf"\g<prefix>{public_nip_base}", updated)
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render public nip.io endpoints from one shared base host."
    )
    parser.add_argument(
        "--base",
        required=True,
        help='Public host base, for example "129.114.26.185.nip.io".',
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root to render inside. Defaults to the current directory.",
    )
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    changed: list[str] = []

    for relative_path in PUBLIC_HOST_FILES:
        path = repo_root / relative_path
        if not path.exists():
            raise FileNotFoundError(f"Expected manifest does not exist: {path}")
        if render_file(path, args.base):
            changed.append(relative_path)

    for relative_path in changed:
        print(relative_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
