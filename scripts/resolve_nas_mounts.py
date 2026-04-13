#!/usr/bin/env python3

import argparse
import shlex
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.deploy_mounts import resolve_nas_mount_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--dist-dir", required=True)
    parser.add_argument("--compose-file", required=True)
    parser.add_argument("--mount-mode", default="auto")
    parser.add_argument("--media-bind-root")
    args = parser.parse_args()

    result = resolve_nas_mount_config(
        source_dir=args.source_dir,
        dist_dir=args.dist_dir,
        compose_file=args.compose_file,
        requested_mode=args.mount_mode,
        media_bind_root=args.media_bind_root,
    )

    print(f"export NOCTRA_SELECTED_MOUNT_MODE={shlex.quote(result['mount_mode'] or '')}")
    print(f"export NOCTRA_SELECTED_COMPOSE_FILE={shlex.quote(result['compose_file'] or '')}")
    if result["media_bind_root"]:
        print(f"export NOCTRA_MEDIA_BIND_ROOT={shlex.quote(result['media_bind_root'])}")
    else:
        print("unset NOCTRA_MEDIA_BIND_ROOT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
