#!/usr/bin/env python3

# action.py: run the sigstore-conformance test suite
#
# all state is passed in as environment variables

import os
import string
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
_TEMPLATES = _HERE / "templates"

_SUMMARY = Path(os.getenv("GITHUB_STEP_SUMMARY")).open("a")  # type: ignore
_RENDER_SUMMARY = os.getenv("GHA_SIGSTORE_CONFORMANCE_SUMMARY", "true") == "true"
_DEBUG = (
    os.getenv("GHA_SIGSTORE_CONFORMANCE_INTERNAL_BE_CAREFUL_DEBUG", "false") != "false"
)
_ACTION_PATH = Path(os.getenv("GITHUB_ACTION_PATH"))  # type: ignore


# TODO(alex): Figure out where to put this.
def _get_oidc_token(gh_token: str):
    from datetime import datetime, timedelta
    from io import BytesIO
    from zipfile import ZipFile

    import requests

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {gh_token}",
    }

    session = requests.Session()
    workflow_time = None
    while workflow_time is None or datetime.now() - workflow_time >= timedelta(
        minutes=5
    ):
        if workflow_time is None:
            _debug("Couldn't find a recent token, waiting...")
            import time

            time.sleep(60)

        resp = session.get(
            url="https://api.github.com/repos/tetsuo-cpp/sigstore-conformance-oidc/"
            "actions/workflows/54271711/runs",
            headers=headers,
        )
        resp.raise_for_status()
        resp_json = resp.json()
        workflow = resp_json["workflow_runs"][0]
        if workflow["status"] != "completed":
            continue
        run_id = workflow["id"]
        workflow_time = datetime.strptime(
            workflow["run_started_at"], "%Y-%m-%dT%H:%M:%SZ"
        )

    resp = session.get(
        url="https://api.github.com/repos/tetsuo-cpp/sigstore-conformance-oidc/actions"
        f"/runs/{run_id}/artifacts",
        headers=headers,
    )
    resp.raise_for_status()
    resp_json = resp.json()
    artifacts = resp_json["artifacts"]
    assert len(artifacts) == 1
    oidc_artifact = artifacts[0]
    assert oidc_artifact["name"] == "oidc-token"
    artifact_id = oidc_artifact["id"]

    resp = session.get(
        url="https://api.github.com/repos/tetsuo-cpp/sigstore-conformance-oidc/actions"
        f"/artifacts/{artifact_id}/zip",
        headers=headers,
    )
    resp.raise_for_status()
    artifact_zip = ZipFile(BytesIO(resp.content))
    artifact = artifact_zip.open("oidc-token.txt")

    # NOTE(alex): Seems to be a newline here.
    return artifact.read().decode()[:-1]


def _template(name):
    path = _TEMPLATES / f"{name}.md"
    return string.Template(path.read_text())


def _summary(msg):
    if _RENDER_SUMMARY:
        print(msg, file=_SUMMARY)


def _debug(msg):
    if _DEBUG:
        print(f"\033[93mDEBUG: {msg}\033[0m", file=sys.stderr)


def _log(msg):
    print(msg, file=sys.stderr)


def _sigstore_conformance(*args):
    return ["pytest", _ACTION_PATH / "test", *args]


def _fatal_help(msg):
    print(f"::error::❌ {msg}")
    sys.exit(1)


sigstore_conformance_args = []

if _DEBUG:
    sigstore_conformance_args.extend(["-s", "-vv", "--showlocals"])

entrypoint = os.getenv("GHA_SIGSTORE_CONFORMANCE_ENTRYPOINT")
if entrypoint:
    sigstore_conformance_args.extend(["--entrypoint", entrypoint])

gh_token = os.getenv("GHA_SIGSTORE_CONFORMANCE_GITHUB_TOKEN")
if gh_token:
    oidc_token = _get_oidc_token(gh_token)
    sigstore_conformance_args.extend(["--identity-token", oidc_token])

_debug(f"running: sigstore-conformance {[str(a) for a in sigstore_conformance_args]}")

status = subprocess.run(
    _sigstore_conformance(*sigstore_conformance_args),
    text=True,
    capture_output=True,
)

_debug(status.stdout)

if status.returncode == 0:
    _summary("🎉 sigstore-conformance exited successfully")
else:
    _summary("❌ sigstore-conformance found one or more test failures")

_summary(
    """
<details>
<summary>
    Raw `sigstore-conformance` output
</summary>

```
    """
)
_log(status.stdout)
_summary(
    """
```
</details>
    """
)

sys.exit(status.returncode)
