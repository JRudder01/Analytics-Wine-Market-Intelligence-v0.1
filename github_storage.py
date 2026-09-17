from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests

from pricing_engine import normalize_comp_data

GITHUB_API = "https://api.github.com"
DEFAULT_BRANCH = "main"
DEFAULT_COMPS_PATH = "data/wine_comps.csv"


@dataclass
class GitHubConfig:
    token: str
    repo: str
    branch: str = DEFAULT_BRANCH
    path: str = DEFAULT_COMPS_PATH


class GitHubStorageError(RuntimeError):
    pass


def _secret(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return str(value).strip()
    try:
        import streamlit as st
        return str(st.secrets.get(name, default)).strip()
    except Exception:
        return str(default).strip()


def get_github_config() -> GitHubConfig | None:
    token = _secret("GITHUB_TOKEN")
    repo = _secret("GITHUB_REPO")
    if not token or not repo:
        return None
    return GitHubConfig(
        token=token,
        repo=repo,
        branch=_secret("GITHUB_BRANCH", DEFAULT_BRANCH) or DEFAULT_BRANCH,
        path=_secret("GITHUB_COMPS_PATH", DEFAULT_COMPS_PATH) or DEFAULT_COMPS_PATH,
    )


def github_storage_status() -> tuple[bool, str]:
    cfg = get_github_config()
    if cfg is None:
        return False, "GitHub write-back is not configured. Add GITHUB_TOKEN and GITHUB_REPO to Streamlit Secrets."
    if "/" not in cfg.repo:
        return False, "GITHUB_REPO must use owner/repository format."
    return True, f"GitHub batch persistence configured for {cfg.repo}:{cfg.branch}/{cfg.path}."


def _headers(cfg: GitHubConfig) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {cfg.token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Rudder-Wine-Market-Intelligence",
    }


def _content_url(cfg: GitHubConfig) -> str:
    return f"{GITHUB_API}/repos/{cfg.repo}/contents/{cfg.path}"


def fetch_remote_comps(cfg: GitHubConfig | None = None) -> tuple[pd.DataFrame, str]:
    cfg = cfg or get_github_config()
    if cfg is None:
        raise GitHubStorageError("GitHub write-back is not configured.")
    response = requests.get(
        _content_url(cfg),
        headers=_headers(cfg),
        params={"ref": cfg.branch},
        timeout=30,
    )
    if response.status_code != 200:
        raise GitHubStorageError(
            f"Could not read {cfg.path} from GitHub ({response.status_code}): {response.text[:400]}"
        )
    payload = response.json()
    sha = payload.get("sha")
    content = payload.get("content")
    if not sha or not content:
        raise GitHubStorageError("GitHub returned the comp file without content/SHA metadata.")
    raw = base64.b64decode(content).decode("utf-8-sig")
    df = pd.read_csv(io.StringIO(raw))
    return normalize_comp_data(df), sha


def merge_remote_and_pending(remote: pd.DataFrame, pending: pd.DataFrame | None) -> pd.DataFrame:
    if pending is None or pending.empty:
        return normalize_comp_data(remote.copy())
    combined = pd.concat([remote, normalize_comp_data(pending)], ignore_index=True)
    combined = normalize_comp_data(combined)

    # Preserve independent sources and historical price changes. Exact repeated rows
    # are collapsed, including rows staged twice in one session.
    identity = [
        "winery", "wine", "vintage", "price", "price_type",
        "source_name", "source_url", "price_date",
    ]
    available = [c for c in identity if c in combined.columns]
    if available:
        combined = combined.drop_duplicates(available, keep="last")
    return combined.reset_index(drop=True)


def _put_file(cfg: GitHubConfig, csv_bytes: bytes, sha: str, message: str) -> dict[str, Any]:
    payload = {
        "message": message,
        "content": base64.b64encode(csv_bytes).decode("ascii"),
        "sha": sha,
        "branch": cfg.branch,
    }
    return requests.put(
        _content_url(cfg),
        headers=_headers(cfg),
        json=payload,
        timeout=30,
    )


def commit_pending_comps(
    pending: pd.DataFrame,
    commit_message: str | None = None,
    cfg: GitHubConfig | None = None,
) -> dict[str, Any]:
    cfg = cfg or get_github_config()
    if cfg is None:
        raise GitHubStorageError("GitHub write-back is not configured.")
    if pending is None or pending.empty:
        raise GitHubStorageError("There are no pending comp changes to commit.")

    remote, sha = fetch_remote_comps(cfg)
    merged = merge_remote_and_pending(remote, pending)
    added_net = max(0, len(merged) - len(remote))
    staged = len(pending)
    message = commit_message or f"Add {staged} staged wine comp observation{'s' if staged != 1 else ''}"
    csv_bytes = merged.to_csv(index=False).encode("utf-8")

    response = _put_file(cfg, csv_bytes, sha, message)
    if response.status_code in (409, 422):
        # One safe retry using the newest remote SHA/file. This prevents an older
        # session from silently replacing changes committed just before this save.
        remote, sha = fetch_remote_comps(cfg)
        merged = merge_remote_and_pending(remote, pending)
        added_net = max(0, len(merged) - len(remote))
        csv_bytes = merged.to_csv(index=False).encode("utf-8")
        response = _put_file(cfg, csv_bytes, sha, message)

    if response.status_code not in (200, 201):
        raise GitHubStorageError(
            f"GitHub commit failed ({response.status_code}): {response.text[:500]}"
        )

    result = response.json()
    commit = result.get("commit") or {}
    return {
        "ok": True,
        "staged_count": staged,
        "remote_before": len(remote),
        "remote_after": len(merged),
        "net_new_rows": added_net,
        "commit_sha": commit.get("sha", ""),
        "commit_url": commit.get("html_url", ""),
        "path": cfg.path,
        "branch": cfg.branch,
        "repo": cfg.repo,
    }
