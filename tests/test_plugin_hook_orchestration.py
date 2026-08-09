"""Lifecycle hooks fire at real apply/verify orchestration boundaries."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from eurika.orchestration.apply_stage import execute_fix_apply_stage


def _configure(tmp_path: Path) -> None:
    (tmp_path / ".eurika").mkdir(exist_ok=True)
    (tmp_path / ".eurika" / "plugins.toml").write_text(
        "\n".join(
            [
                "[[hooks]]",
                'event = "after_apply"',
                'entry_point = "tests.fixtures.eurika_hook_example:capture"',
                "",
                "[[hooks]]",
                'event = "after_verify"',
                'entry_point = "tests.fixtures.eurika_hook_example:capture"',
            ]
        ),
        encoding="utf-8",
    )


def test_apply_and_verify_hooks_fire_in_canonical_order(tmp_path: Path) -> None:
    from tests.fixtures import eurika_hook_example as example

    example.reset()
    _configure(tmp_path)
    (tmp_path / "foo.py").write_text("import os\n", encoding="utf-8")
    operations = [
        {
            "target_file": "foo.py",
            "kind": "remove_unused_import",
            "module": "os",
            "explainability": {},
        }
    ]
    plan = {"project_root": str(tmp_path), "operations": operations}

    def fake_apply(*_args, **kwargs):
        report = {
            "modified": ["foo.py"],
            "skipped": [],
            "errors": [],
            "verify": {"success": True},
            "run_id": "hook-run",
            "verify_duration_ms": 1,
        }
        kwargs["on_after_apply"](report)
        return report

    result = type("R", (), {"output": {"policy_decisions": []}})()
    report, modified, verified = execute_fix_apply_stage(
        tmp_path,
        plan,
        operations,
        session_id="s1",
        quiet=True,
        verify_cmd=None,
        verify_timeout=None,
        backup_dir=".eurika_backups",
        apply_and_verify=fake_apply,
        run_scan=lambda *_a, **_k: 0,
        build_snapshot_from_self_map=lambda *_a: {},
        diff_architecture_snapshots=lambda *_a: {},
        metrics_from_graph=lambda *_a: {},
        rollback_patch=lambda *_a: {},
        result=result,
    )

    assert modified == ["foo.py"]
    assert verified is True
    assert [row["event"] for row in report["plugin_hooks"]] == [
        "after_apply",
        "after_verify",
    ]
    assert [row["event"] for row in example.EVENTS] == [
        "after_apply",
        "after_verify",
    ]


def test_final_filtered_plan_dispatches_after_plan(tmp_path: Path) -> None:
    from eurika.orchestration.prepare import prepare_fix_cycle_operations
    from tests.fixtures import eurika_hook_example as example

    example.reset()
    (tmp_path / ".eurika").mkdir()
    (tmp_path / ".eurika" / "plugins.toml").write_text(
        "\n".join(
            [
                "[[hooks]]",
                'event = "after_plan"',
                'entry_point = "tests.fixtures.eurika_hook_example:capture"',
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("import os\n", encoding="utf-8")
    fake_result = SimpleNamespace(
        success=True,
        output={
            "proposals": [
                {
                    "action": "suggest_patch_plan",
                    "arguments": {
                        "patch_plan": {
                            "project_root": str(tmp_path),
                            "operations": [
                                {
                                    "kind": "remove_unused_import",
                                    "target_file": "a.py",
                                    "module": "os",
                                }
                            ],
                        }
                    },
                }
            ]
        },
    )
    with patch(
        "eurika.orchestration.prepare.run_fix_diagnose_stage",
        return_value=fake_result,
    ):
        early, result, plan, operations = prepare_fix_cycle_operations(
            tmp_path,
            runtime_mode="assist",
            session_id="s1",
            window=5,
            quiet=True,
            skip_scan=True,
            no_clean_imports=True,
            no_code_smells=True,
            run_scan=lambda *_a, **_k: 0,
        )

    assert early is None
    assert plan is not None
    assert operations
    assert [row["event"] for row in example.EVENTS] == ["after_plan"]
    assert example.EVENTS[0]["payload"]["operations_count"] == 1
    assert result.output["plugin_hooks"][0]["event"] == "after_plan"


def test_simulation_abort_emits_no_apply_or_verify_hooks(
    tmp_path: Path, monkeypatch
) -> None:
    from tests.fixtures import eurika_hook_example as example

    example.reset()
    _configure(tmp_path)
    operations = [{"target_file": "missing.py", "kind": "remove_unused_import"}]
    plan = {"project_root": str(tmp_path), "operations": operations}
    monkeypatch.setattr(
        "patch_engine.simulate_patch",
        lambda *_a, **_k: {
            "errors": ["unsafe"],
            "would_skip": [],
            "skipped_reasons": {},
        },
    )

    report, _, verified = execute_fix_apply_stage(
        tmp_path,
        plan,
        operations,
        session_id=None,
        quiet=True,
        verify_cmd=None,
        verify_timeout=None,
        backup_dir=".eurika_backups",
        apply_and_verify=lambda *_a, **_k: {},
        run_scan=lambda *_a, **_k: 0,
        build_snapshot_from_self_map=lambda *_a: {},
        diff_architecture_snapshots=lambda *_a: {},
        metrics_from_graph=lambda *_a: {},
        rollback_patch=lambda *_a: {},
        result=type("R", (), {"output": {"policy_decisions": []}})(),
    )

    assert verified is False
    assert report["aborted_reason"] == "simulation_errors"
    assert example.EVENTS == []
