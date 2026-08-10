#!/usr/bin/env python3
"""Tests for local Friday orchestration tools."""

import json
import unittest

import friday_mcp_proxy as proxy


def response(request_id, payload):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
    }


class FridayProxyTests(unittest.TestCase):
    def setUp(self):
        self.original_email = proxy.ASSIGNEE_EMAIL
        self.original_column = proxy.ASSIGNEE_COLUMN
        proxy.ASSIGNEE_EMAIL = "developer@example.com"
        proxy.ASSIGNEE_COLUMN = ""

    def tearDown(self):
        proxy.ASSIGNEE_EMAIL = self.original_email
        proxy.ASSIGNEE_COLUMN = self.original_column

    def test_tools_list_includes_assignment_tool(self):
        def fake_post(message):
            return {"jsonrpc": "2.0", "id": message["id"], "result": {"tools": []}}

        result = proxy.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, fake_post)

        self.assertEqual(result["result"]["tools"], [proxy.ASSIGN_TOOL])

    def test_assignment_resolves_member_and_people_column(self):
        calls = []

        def fake_post(message):
            calls.append(message)
            name = message["params"]["name"]
            if name == "list_workspace_members":
                return response(message["id"], [{"id": 31, "email": "developer@example.com"}])
            if name == "list_columns":
                return response(message["id"], [{"id": 200, "name": "Responsável", "type": "people"}])
            if name == "update_cell_value":
                return response(message["id"], {"success": True})
            raise AssertionError(name)

        result = proxy.assign_configured_user(
            {"workspace_id": 37, "board_id": 46, "item_id": 1234}, fake_post
        )

        self.assertTrue(result["assigned"])
        self.assertEqual(result["member_id"], 31)
        self.assertEqual(
            calls[-1]["params"]["arguments"],
            {"item_id": 1234, "column_id": 200, "value": "31"},
        )


if __name__ == "__main__":
    unittest.main()
