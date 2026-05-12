import json
import subprocess
from dataclasses import dataclass

QUERY = """
query {
  search(query: "author:@me is:pr state:open archived:false", type: ISSUE, first: 100) {
    nodes {
      ... on PullRequest {
        number
        title
        url
        isCrossRepository
        headRefName
        baseRepository { name owner { login } }
        headRepository { name url }
        headRepositoryOwner { login }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class OpenPR:
    number: int
    title: str
    url: str
    base_owner: str
    base_repo: str
    head_branch: str
    is_fork: bool
    fork_clone_url: str | None

    @property
    def base_slug(self) -> str:
        return f"{self.base_owner}/{self.base_repo}"


class GhError(RuntimeError):
    pass


def check_auth() -> None:
    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GhError(
            "gh is not authenticated. Run `gh auth login` and re-try.\n" + result.stderr.strip()
        )


def list_open_prs() -> list[OpenPR]:
    try:
        result = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={QUERY}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise GhError(f"gh api graphql failed: {error.stderr.strip()}") from error
    payload = json.loads(result.stdout)
    if "errors" in payload:
        raise GhError(f"graphql errors: {payload['errors']}")
    nodes = payload["data"]["search"]["nodes"]
    out: list[OpenPR] = []
    for node in nodes:
        if not node:
            continue
        head_repo = node.get("headRepository") or {}
        out.append(
            OpenPR(
                number=node["number"],
                title=node["title"],
                url=node["url"],
                base_owner=node["baseRepository"]["owner"]["login"],
                base_repo=node["baseRepository"]["name"],
                head_branch=node["headRefName"],
                is_fork=bool(node["isCrossRepository"]),
                fork_clone_url=(f"{head_repo['url']}.git" if node["isCrossRepository"] and head_repo else None),
            )
        )
    return out
