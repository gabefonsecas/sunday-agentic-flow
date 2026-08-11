import os
import unittest
from unittest.mock import MagicMock, patch

from sunday.adapters.friday import FridayAdapter, FridayMCPClient, resolve_user_from_tasks


class FakeClient:
    def __init__(self, user_id=7, tasks=True):
        self.user_id = user_id
        self.tasks = tasks
        self.calls = []

    def tool(self, name, arguments=None):
        self.calls.append((name, arguments or {}))
        if name == "get_current_user":
            raise RuntimeError("unknown tool")
        if name == "list_my_tasks":
            return [{"id": 42, "responsaveis": [{"id": self.user_id, "email": f"u{self.user_id}@test"}]}] if self.tasks else []
        if name == "list_workspace_members":
            return [{"id": self.user_id, "email": f"u{self.user_id}@test"}, {"id": 9, "email": "fallback@test"}]
        if name == "list_columns":
            return [
                {"id": 11, "name": "Owner", "type": "people"},
                {"id": 201, "name": "Status", "type": "status"},
            ]
        if name == "update_cell_value":
            return {"success": True}
        if name == "list_groups":
            return [{"id": 3}]
        if name == "list_items":
            return [{"id": 99, "name": "Unassigned"}]
        raise AssertionError(name)


class FridayAdapterTests(unittest.TestCase):
    def test_empty_notification_response_is_supported(self):
        client = FridayMCPClient("https://friday.test/sse")
        client.endpoint = "https://friday.test/message"
        client.ready.set()
        client.thread = MagicMock()
        client.thread.is_alive.return_value = True
        response = MagicMock()
        response.read.return_value = b""
        context = MagicMock()
        context.__enter__.return_value = response
        with patch("sunday.adapters.friday.urllib.request.urlopen", return_value=context):
            self.assertEqual(client.request("notifications/initialized"), {})

    def test_each_token_resolves_its_own_user(self):
        first = FridayAdapter(FakeClient(7)).get_current_user(1)
        second = FridayAdapter(FakeClient(8)).get_current_user(1)
        self.assertEqual(first["id"], 7)
        self.assertEqual(second["id"], 8)
        self.assertNotEqual(first["email"], second["email"])

    def test_no_fixed_user_id_exists(self):
        user = resolve_user_from_tasks([{"responsaveis": [{"id": 912, "email": "dynamic@test"}]}])
        self.assertEqual(user["id"], 912)

    def test_taskless_token_uses_validated_email_fallback(self):
        with patch.dict(os.environ, {"FRIDAY_FALLBACK_ASSIGNEE_EMAIL": "fallback@test"}, clear=False):
            user = FridayAdapter(FakeClient(tasks=False)).get_current_user(1)
        self.assertEqual(user["id"], 9)
        self.assertEqual(user["identity_source"], "configured fallback email")

    def test_unassigned_task_is_found_from_board_groups(self):
        task = FridayAdapter(FakeClient()).get_task("99", board_id=2)
        self.assertEqual(task["id"], 99)

    def test_claim_uses_resolved_token_user(self):
        client = FakeClient(73)
        result = FridayAdapter(client).claim_task({"id": 42}, 1, 2)
        self.assertEqual(result["member_id"], 73)
        update = [call for call in client.calls if call[0] == "update_cell_value"][-1]
        self.assertEqual(update[1]["value"], "73")

    def test_status_update_resolves_column_by_id(self):
        client = FakeClient()
        FridayAdapter(client).set_status(42, 46, "201", "working")
        update = [call for call in client.calls if call[0] == "update_cell_value"][-1]
        self.assertEqual(update[1], {"item_id": 42, "column_id": 201, "value": "working"})
