import os
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest
from unittest.mock import MagicMock, patch

from sunday.adapters.friday import FridayAdapter, FridayMCPClient, resolve_user_from_tasks
from sunday.errors import AuthenticationError, TransientIntegrationError
from sunday.friday_proxy import handle_message


class FridayHandler(BaseHTTPRequestHandler):
    failures = 0
    posts = 0

    def log_message(self, *_args):
        pass

    def do_GET(self):
        endpoint = f"http://127.0.0.1:{self.server.server_port}/messages"
        body = f"event: endpoint\ndata: {endpoint}\n\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        type(self).posts += 1
        if type(self).failures:
            type(self).failures -= 1
            self.send_response(503)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        body = json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": {"ok": True}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


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
            if isinstance(self.tasks, list):
                return self.tasks
            return [{"id": 42, "responsaveis": [{"id": self.user_id, "email": f"u{self.user_id}@test"}]}] if self.tasks else []
        if name == "list_workspace_members":
            return [{"id": self.user_id, "email": f"u{self.user_id}@test"}, {"id": 9, "email": "fallback@test"}]
        if name == "list_columns":
            return [
                {"id": 11, "name": "Owner", "type": "people"},
                {"id": 201, "name": "Status", "type": "status"},
                {"id": 298, "name": "IA", "type": "checkbox"},
            ]
        if name == "update_cell_value":
            return {"success": True}
        if name == "list_groups":
            return [{"id": 3}]
        if name == "list_items":
            return [{"id": 99, "name": "Unassigned"}]
        raise AssertionError(name)


class FridayAdapterTests(unittest.TestCase):
    def test_real_sse_transport_retries_and_closes(self):
        FridayHandler.failures = 1
        FridayHandler.posts = 0
        server = ThreadingHTTPServer(("127.0.0.1", 0), FridayHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = FridayMCPClient(
            f"http://127.0.0.1:{server.server_port}/sse",
            timeout=2, retries=2, backoff=0,
        )
        try:
            self.assertEqual(client.request("ping", retry_safe=True), {"ok": True})
            self.assertEqual(client.retry_count, 1)
            self.assertEqual(FridayHandler.posts, 2)
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_authentication_failure_is_not_retried(self):
        response = MagicMock()
        response.__enter__.side_effect = __import__("urllib.error").error.HTTPError(
            "https://friday.test", 401, "unauthorized", {}, None
        )
        client = FridayMCPClient("https://friday.test/sse", timeout=0.1, retries=2, backoff=0)
        client.endpoint = "https://friday.test/messages"
        client.ready.set()
        client.thread = MagicMock()
        client.thread.is_alive.return_value = True
        with patch("sunday.adapters.friday.urllib.request.urlopen", return_value=response):
            with self.assertRaises(AuthenticationError):
                client.request("ping")

    def test_mutating_tool_is_never_retried_after_uncertain_response(self):
        client = FridayMCPClient(
            "https://friday.test/sse", timeout=0.1, retries=3, backoff=0,
        )
        applied = []

        def lost_response(method, params):
            applied.append((method, params["name"]))
            raise TransientIntegrationError("response lost after apply")

        with patch.object(client, "_request_once", side_effect=lost_response):
            with self.assertRaises(TransientIntegrationError):
                client.tool("create_item", {"name": "once"})
        self.assertEqual(applied, [("tools/call", "create_item")])
        self.assertEqual(client.retry_count, 0)

    def test_stdio_proxy_marks_mutating_tool_call_as_not_retry_safe(self):
        client = MagicMock()
        client.request.return_value = {"content": []}
        handle_message(
            {
                "id": 1, "method": "tools/call",
                "params": {"name": "create_item", "arguments": {}},
            },
            client,
        )
        self.assertFalse(client.request.call_args.kwargs["retry_safe"])

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

    def test_claim_reconciliation_uses_token_identity(self):
        result = FridayAdapter(FakeClient(73)).reconcile_claim("42", 1, 2, "owner")
        self.assertTrue(result["reconciled"])
        self.assertEqual(result["member_id"], 73)

    def test_status_update_resolves_column_by_id(self):
        client = FakeClient()
        FridayAdapter(client).set_status(42, 46, "201", "working")
        update = [call for call in client.calls if call[0] == "update_cell_value"][-1]
        self.assertEqual(update[1], {"item_id": 42, "column_id": 201, "value": "working"})

    def test_watcher_uses_all_non_completed_tasks_from_selected_board(self):
        tasks = [
            {"id": 1, "board_id": 46, "status": {"id": "working"}},
            {"id": 2, "board_id": 46, "status": {"id": "done"}},
            {"id": 3, "board_id": 99, "status": {"id": "working"}},
        ]
        ready = FridayAdapter(FakeClient(tasks=tasks)).list_ready_tasks(
            "", 46, "done"
        )
        self.assertEqual([task["id"] for task in ready], [1])

    def test_ai_checkbox_is_written_as_audit_marker(self):
        client = FakeClient()
        FridayAdapter(client).mark_ai(42, 46, "298")
        update = [call for call in client.calls if call[0] == "update_cell_value"][-1]
        self.assertEqual(update[1], {"item_id": 42, "column_id": 298, "value": "true"})
