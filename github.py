import base64
import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_API_BASE = "https://api.github.com"
_DEFAULT_BRANCH = "main"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_token() -> str:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise EnvironmentError(
            "GITHUB_TOKEN environment variable is not set or empty."
        )
    return token


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _raise_for_status(response: requests.Response, context: str) -> None:
    if not response.ok:
        try:
            detail = response.json().get("message", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(f"{context} — HTTP {response.status_code}: {detail}")


def _get_authenticated_user(headers: dict) -> str:
    resp = requests.get(f"{_API_BASE}/user", headers=headers, timeout=10)
    _raise_for_status(resp, "Failed to fetch authenticated user")
    return resp.json()["login"]


def _create_repo(repo_name: str, headers: dict) -> str:
    payload = {
        "name": repo_name,
        "description": "Auto-generated backend project",
        "private": False,
        "auto_init": False,
    }
    resp = requests.post(
        f"{_API_BASE}/user/repos",
        headers=headers,
        json=payload,
        timeout=15,
    )
    _raise_for_status(resp, f"Failed to create repository '{repo_name}'")
    data = resp.json()
    logger.info("github | repository created: %s", data["html_url"])
    return data["html_url"]


def _push_file(
    owner: str,
    repo_name: str,
    rel_path: str,
    content: str,
    headers: dict,
) -> None:
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    url = f"{_API_BASE}/repos/{owner}/{repo_name}/contents/{rel_path}"
    payload = {
        "message": f"Add {rel_path}",
        "content": encoded,
        "branch": _DEFAULT_BRANCH,
    }
    resp = requests.put(url, headers=headers, json=payload, timeout=15)
    _raise_for_status(resp, f"Failed to push '{rel_path}'")
    logger.debug("github | pushed %s", rel_path)


def _collect_files(project_path: Path) -> list[tuple[str, str]]:
    """Return [(relative_posix_path, content), ...] for every file under project_path."""
    collected: list[tuple[str, str]] = []
    for file in sorted(project_path.rglob("*")):
        if not file.is_file():
            continue
        rel = file.relative_to(project_path).as_posix()
        try:
            content = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("github | skipping %s — cannot read: %s", rel, exc)
            continue
        collected.append((rel, content))
    return collected


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def github_push(project_path: str) -> str:
    """
    Create a new GitHub repository and push every file from project_path.

    Parameters
    ----------
    project_path:
        Absolute or relative path to the local project folder.

    Returns
    -------
    HTML URL of the newly created repository (e.g. https://github.com/user/repo).

    Raises
    ------
    EnvironmentError  — GITHUB_TOKEN not set.
    ValueError        — project_path is empty or does not exist.
    RuntimeError      — any GitHub API call fails.
    """
    if not project_path or not project_path.strip():
        raise ValueError("project_path must not be empty.")

    root = Path(project_path).resolve()
    if not root.exists():
        raise ValueError(f"project_path does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"project_path is not a directory: {root}")

    token     = _get_token()
    hdrs      = _headers(token)
    repo_name = root.name  # e.g. "generated_backend"

    logger.info("github | authenticating …")
    owner = _get_authenticated_user(hdrs)
    logger.info("github | authenticated as %s", owner)

    repo_url = _create_repo(repo_name, hdrs)

    files = _collect_files(root)
    if not files:
        raise ValueError(f"No readable files found in: {root}")

    logger.info("github | pushing %d file(s) to %s/%s", len(files), owner, repo_name)
    failed: list[str] = []

    for rel_path, content in files:
        try:
            _push_file(owner, repo_name, rel_path, content, hdrs)
        except RuntimeError as exc:
            logger.error("github | %s", exc)
            failed.append(rel_path)

    if failed:
        logger.warning(
            "github | %d file(s) failed to push:\n%s",
            len(failed), "\n".join(failed),
        )

    if len(failed) == len(files):
        raise RuntimeError("All file pushes failed — repository may be incomplete.")

    logger.info("github | push complete → %s", repo_url)
    return repo_url
