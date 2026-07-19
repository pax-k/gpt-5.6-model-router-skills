from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "workflow-scenarios.json"
SCRIPTS = ROOT / "plugins/gpt-5-6-model-router/skills/route-gpt56-task/scripts"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


route_task = _load_module("workflow_fixture_route_task", SCRIPTS / "route_task.py")
orchestrate = _load_module("workflow_fixture_orchestrate", SCRIPTS / "orchestrate.py")


def _merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        result = copy.deepcopy(base)
        for key, value in override.items():
            result[key] = _merge(result[key], value) if key in result else copy.deepcopy(value)
        return result
    return copy.deepcopy(override)


def _resolve(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        return ids[value[1:]]
    if isinstance(value, list):
        return [_resolve(item, ids) for item in value]
    if isinstance(value, dict):
        return {key: _resolve(item, ids) for key, item in value.items()}
    return value


def _read_path(value: Any, path: str) -> Any:
    current = value
    for segment in path.split("."):
        current = current[int(segment)] if isinstance(current, list) else current[segment]
    return current


class WorkflowFixtureTests(unittest.TestCase):
    """Execute the documented workflow catalog against the public runtime APIs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(FIXTURE.read_text())

    def _inputs(self, scenario: dict[str, Any]) -> dict[str, Any]:
        defaults = self.payload["defaults"]
        overrides = scenario.get("inputs", {})
        inputs = _merge(defaults, overrides)
        for name, profile in overrides.items():
            if name.endswith("route_profile") and name != "route_profile":
                inputs[name] = _merge(defaults["route_profile"], profile)
        return _resolve(inputs, self.payload["ids"])

    def _execute(self, scenario: dict[str, Any]) -> dict[str, Any]:
        inputs = self._inputs(scenario)
        values: dict[str, Any] = {}
        for action in scenario["actions"]:
            action = _resolve(action, self.payload["ids"])
            operation = action["operation"]
            if operation == "route":
                result = route_task.decide(inputs[action.get("input", "route_profile")])
            elif operation == "initialize":
                result = orchestrate.initialize(inputs["orchestration_profile"])
            elif operation == "ready":
                result = orchestrate.ready(values[action["state"]])
            elif operation == "apply_event":
                event = _merge(inputs["event"], action.get("event", {}))
                result = orchestrate.apply_event(values[action["state"]], event)
            elif operation == "status":
                result = orchestrate.status(values[action["state"]])
            elif operation == "complete_check":
                result = orchestrate.complete_check(values[action["state"]], action.get("actor", "root"))
            elif operation == "control":
                result = orchestrate.apply_control(values[action["state"]], action["control"])
            elif operation == "authorize_from_decision":
                result = orchestrate.apply_control(
                    values[action["state"]],
                    {
                        "action": "authorize_delegation",
                        "task_ids": [action["task_id"]],
                        "capability": values[action["decision"]]["delegation_capability"],
                    },
                )
            elif operation == "persist_and_reload":
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "state.json"
                    orchestrate.persist(values[action["state"]], path)
                    result = orchestrate.load_json(path)
            else:
                self.fail(f"{scenario['id']}: unsupported fixture operation: {operation}")
            values[action["save"]] = result
        return values

    def test_every_documented_workflow_executes_its_runtime_scenario(self) -> None:
        scenarios = self.payload["scenarios"]
        self.assertEqual(self.payload["schema_version"], 2)
        self.assertEqual(len(scenarios), 25)
        self.assertEqual([scenario["id"][:3] for scenario in scenarios], [f"{number:02d}-" for number in range(1, 26)])

        for scenario in scenarios:
            with self.subTest(scenario=scenario["id"]):
                values = self._execute(scenario)
                self.assertTrue(scenario["actions"], "scenario must perform production runtime actions")
                for expected in scenario["expected"]:
                    actual = _read_path(values[expected["source"]], expected["path"])
                    if "equals" in expected:
                        self.assertEqual(actual, expected["equals"], expected["path"])
                    if "contains" in expected:
                        self.assertIn(expected["contains"], actual, expected["path"])

    def test_fixture_declares_only_real_runtime_limitations(self) -> None:
        """Keep unsupported documented transitions visible until production adds them."""
        limitations = {
            scenario["id"]: scenario.get("runtime_limitations", [])
            for scenario in self.payload["scenarios"]
            if scenario.get("runtime_limitations")
        }
        self.assertEqual(limitations, {})


if __name__ == "__main__":
    unittest.main()
