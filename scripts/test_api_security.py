from __future__ import annotations

import random
import string
import unittest
from unittest.mock import Mock, patch

import check_transition as ct


class ApiGetSecurityTests(unittest.TestCase):
    def assert_rejected_without_network(self, url: str) -> None:
        with patch.object(ct, "HTTPSConnection") as connection_factory:
            payload, errors = ct.api_get(url, "test-token", "test request")
        self.assertIsNone(payload)
        self.assertTrue(any("approved HTTPS api.github.com endpoint set" in error for error in errors))
        connection_factory.assert_not_called()

    def test_rejects_plain_http_before_network(self):
        self.assert_rejected_without_network(
            "http://api.github.com/repos/example/repo/pulls/7"
        )

    def test_rejects_non_github_host_before_network(self):
        self.assert_rejected_without_network(
            "https://example.com/repos/example/repo/pulls/7"
        )

    def test_rejects_unapproved_github_api_path_before_network(self):
        self.assert_rejected_without_network(
            "https://api.github.com/user"
        )

    def test_rejects_query_or_fragment_before_network(self):
        self.assert_rejected_without_network(
            "https://api.github.com/repos/example/repo/pulls/7?x=1"
        )
        self.assert_rejected_without_network(
            "https://api.github.com/repos/example/repo/pulls/7#fragment"
        )

    def test_generated_out_of_policy_urls_never_open_network(self):
        """Exercise hundreds of deterministic URL mutations without networking."""
        rng = random.Random(20260903)
        alphabet = string.ascii_letters + string.digits + "-._~%"
        valid_paths = (
            "/repos/example/repo/pulls/7",
            "/repos/example/repo/issues/comments/123",
        )
        urls: set[str] = set()

        for _ in range(80):
            marker = "".join(rng.choice(alphabet) for _ in range(rng.randint(4, 24)))
            valid_path = rng.choice(valid_paths)
            urls.update(
                {
                    f"http://api.github.com{valid_path}",
                    f"ftp://api.github.com{valid_path}",
                    f"https://api.github.com.evil.invalid{valid_path}",
                    f"https://localhost{valid_path}",
                    f"https://api.github.com/repos/example/repo/not-approved/{marker}",
                    f"https://api.github.com{valid_path}?q={marker}",
                    f"https://api.github.com{valid_path}#{marker}",
                }
            )

        self.assertGreaterEqual(len(urls), 200)
        for url in sorted(urls):
            with self.subTest(url=url):
                self.assert_rejected_without_network(url)

    def test_generated_allowed_paths_use_only_fixed_github_host(self):
        """Generate valid allow-listed paths and prove they use the fixed TLS host."""
        rng = random.Random(20260903)
        alphabet = string.ascii_lowercase + string.digits

        for _ in range(40):
            owner = "o" + "".join(rng.choice(alphabet) for _ in range(8))
            repo = "r" + "".join(rng.choice(alphabet) for _ in range(8))
            number = rng.randint(1, 999999)
            paths = (
                f"/repos/{owner}/{repo}/pulls/{number}",
                f"/repos/{owner}/{repo}/issues/comments/{number}",
            )

            for path in paths:
                response = Mock(status=200)
                response.read.return_value = b'{"ok": true}'
                connection = Mock()
                connection.getresponse.return_value = response

                with self.subTest(path=path):
                    with patch.object(
                        ct, "HTTPSConnection", return_value=connection
                    ) as factory:
                        payload, errors = ct.api_get(
                            f"https://api.github.com{path}",
                            "test-token",
                            "generated allowed endpoint",
                        )

                    self.assertEqual(errors, [])
                    self.assertEqual(payload, {"ok": True})
                    factory.assert_called_once_with("api.github.com", timeout=15)
                    connection.request.assert_called_once()
                    method, requested_path = connection.request.call_args.args[:2]
                    self.assertEqual(method, "GET")
                    self.assertEqual(requested_path, path)
                    connection.close.assert_called_once_with()

    def test_allowed_pull_endpoint_uses_fixed_github_https_connection(self):
        response = Mock(status=200)
        response.read.return_value = b'{"ok": true}'
        connection = Mock()
        connection.getresponse.return_value = response

        with patch.object(ct, "HTTPSConnection", return_value=connection) as factory:
            payload, errors = ct.api_get(
                "https://api.github.com/repos/example/repo/pulls/7",
                "test-token",
                "PR #7",
            )

        self.assertEqual(errors, [])
        self.assertEqual(payload, {"ok": True})
        factory.assert_called_once_with("api.github.com", timeout=15)
        connection.request.assert_called_once()
        method, path = connection.request.call_args.args[:2]
        self.assertEqual(method, "GET")
        self.assertEqual(path, "/repos/example/repo/pulls/7")
        self.assertEqual(
            connection.request.call_args.kwargs["headers"]["Authorization"],
            "Bearer test-token",
        )
        connection.close.assert_called_once_with()

    def test_allowed_issue_comment_endpoint_uses_fixed_github_host(self):
        response = Mock(status=200)
        response.read.return_value = b'{"id": 123}'
        connection = Mock()
        connection.getresponse.return_value = response

        with patch.object(ct, "HTTPSConnection", return_value=connection) as factory:
            payload, errors = ct.api_get(
                "https://api.github.com/repos/example/repo/issues/comments/123",
                "test-token",
                "owner approval comment",
            )

        self.assertEqual(errors, [])
        self.assertEqual(payload, {"id": 123})
        factory.assert_called_once_with("api.github.com", timeout=15)
        connection.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
