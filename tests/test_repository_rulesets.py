import json
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).parents[1]
RULESETS_DIRECTORY = REPOSITORY_ROOT / ".github" / "rulesets"
WORKFLOWS_DIRECTORY = REPOSITORY_ROOT / ".github" / "workflows"


def _ruleset(filename: str) -> dict[str, Any]:
    return json.loads((RULESETS_DIRECTORY / filename).read_text(encoding="utf-8"))


def test_main_requires_pull_request_and_every_pull_request_job() -> None:
    ruleset = _ruleset("github-main-ruleset.json")
    rules = {rule["type"]: rule for rule in ruleset["rules"]}
    status_checks = rules["required_status_checks"]["parameters"]["required_status_checks"]
    contexts = {item["context"] for item in status_checks}

    assert ruleset["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]
    assert "pull_request" in rules
    assert contexts == {"Pre-commit", "All tests"}
    assert rules["required_status_checks"]["parameters"]["strict_required_status_checks_policy"]
    assert ruleset["bypass_actors"] == [
        {"actor_id": 0, "actor_type": "Integration", "bypass_mode": "always"}
    ]


def test_only_admins_can_merge_pull_requests_into_main() -> None:
    ruleset = _ruleset("github-main-admin-only-ruleset.json")

    assert ruleset["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]
    assert ruleset["rules"] == [
        {"type": "update", "parameters": {"update_allows_fetch_and_merge": False}}
    ]
    assert ruleset["bypass_actors"] == [
        {
            "actor_id": 5,
            "actor_type": "RepositoryRole",
            "bypass_mode": "pull_request",
        },
        {
            "actor_id": 0,
            "actor_type": "Integration",
            "bypass_mode": "always",
        },
    ]


def test_github_test_jobs_exclude_live_remote_endpoints() -> None:
    for filename in ("pull-request.yml", "release.yml"):
        workflow = (WORKFLOWS_DIRECTORY / filename).read_text(encoding="utf-8")

        assert '-m "not live"' in workflow
        assert "DW_LIVE_" not in workflow
        assert "Run unit, integration, and offline E2E tests" in workflow
