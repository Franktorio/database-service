"""Contract test shared by every reusable backend."""

import unittest

from starlette.requests import Request

from src.services.system.monitoring import get_monitoring_service, monitored


class MonitoringContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_is_versioned_timestamped_and_keeps_http_method(self):
        @monitored(measuring="api", operation_type="read")
        async def sample_endpoint(request):
            return {"ok": True}

        request = Request({"type": "http", "method": "PATCH", "headers": [], "client": ("127.0.0.1", 1)})
        await sample_endpoint(request)
        snapshot = get_monitoring_service().get_snapshot()

        self.assertEqual(snapshot["schema_version"], 1)
        self.assertIn("generated_at", snapshot)
        self.assertIn("metrics", snapshot)
        self.assertEqual(snapshot["recent"]["api"][-1]["method"], "PATCH")
        self.assertIn("recorded_at", snapshot["recent"]["api"][-1])
        self.assertIn("database", snapshot["recent"])
        self.assertIn("redis", snapshot["recent"])


if __name__ == "__main__":
    unittest.main()
