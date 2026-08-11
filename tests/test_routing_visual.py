import tempfile
from dataclasses import asdict
from pathlib import Path
import unittest

from sunday.cli import parser
from sunday.routing import ModelRouter
from sunday.state import RunStore
from sunday.visual import render_routes, route_data


class RoutingPoolTests(unittest.TestCase):
    def test_codex_retries_escalate_across_pool(self):
        router = ModelRouter("codex")
        routes = [router.route("discovery", attempt) for attempt in (1, 2, 3)]
        self.assertEqual(
            [route.model for route in routes],
            ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"],
        )
        self.assertEqual([route.pool_position for route in routes], [1, 2, 3])

    def test_high_risk_starts_above_cheapest_candidate(self):
        route = ModelRouter("codex").route("implementation", risk="high")
        self.assertEqual(route.model, "gpt-5.6-sol")
        self.assertEqual(route.reason, "high risk escalation")

    def test_gemini_and_antigravity_have_three_candidates(self):
        for host in ("gemini", "antigravity"):
            router = ModelRouter(host)
            for phase in ("discovery", "implementation", "verification", "review"):
                self.assertEqual(len(router.pool(phase)), 3)


class VisualRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RunStore(Path(self.temp.name) / "sunday.db")
        self.run = self.store.create("42", "demo", "codex")
        first = ModelRouter("codex").route("discovery", 1)
        second = ModelRouter("codex").route("discovery", 2)
        self.store.event(self.run.id, "route.started", "discovery", asdict(first))
        self.store.event(self.run.id, "route.completed", "discovery", {
            **asdict(first),
            "accepted": False, "duration_seconds": 1.0,
        })
        self.store.event(self.run.id, "route.started", "discovery", asdict(second))
        self.store.event(self.run.id, "route.completed", "discovery", {
            **asdict(second),
            "accepted": True, "observed_model": second.model, "duration_seconds": 2.0,
        })

    def tearDown(self):
        self.temp.cleanup()

    def test_terminal_shows_used_transition_and_available_pool(self):
        output = render_routes(self.store, self.run.id)
        self.assertIn("gpt-5.6-luna -> gpt-5.6-terra", output)
        self.assertIn("gpt-5.6-luna -> gpt-5.6-terra -> gpt-5.6-sol", output)

    def test_mermaid_and_json_formats_are_available(self):
        self.assertIn("flowchart LR", render_routes(self.store, self.run.id, "mermaid"))
        self.assertEqual(route_data(self.store, self.run.id)["phases"][0]["status"], "completed")
        self.assertIn('"host": "codex"', render_routes(self.store, self.run.id, "json"))

    def test_cli_exposes_routes_and_visual_status(self):
        self.assertEqual(parser().parse_args(["routes", "abc"]).command, "routes")
        self.assertTrue(parser().parse_args(["status", "abc", "--visual"]).visual)
