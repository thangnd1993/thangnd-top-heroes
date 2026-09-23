from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_active_developer_reviewer_subagent_routing_remains():
    assert not (ROOT / ".codex/agents/auto-top-heroes-developer.toml").exists()
    assert not (ROOT / ".codex/agents/auto-top-heroes-reviewer.toml").exists()
    config = (ROOT / ".codex/config.toml").read_text(encoding="utf-8-sig").casefold()
    instructions = (ROOT / "AGENTS.md").read_text(encoding="utf-8").casefold()
    workflow = (ROOT / "docs/codex-agent-workflow.md").read_text(encoding="utf-8").casefold()
    for content in (config, instructions, workflow):
        assert "auto-top-heroes-developer" not in content
        assert "auto-top-heroes-reviewer" not in content
        assert "max_concurrent_threads_per_session" not in content
    assert "one codex agent" in workflow
    assert "single-agent" in instructions
