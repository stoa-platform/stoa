"""Transport TLS properties are independent of the host CA store."""

import os
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from keycloak_migration.transport import Admin


class MigrationTransportTests(unittest.TestCase):
    def test_default_certs_requested_without_key_logging(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keylog.txt"
            with (
                patch.dict(os.environ, {"SSLKEYLOGFILE": str(path)}),
                patch.object(ssl.SSLContext, "load_default_certs", autospec=True) as load,
            ):
                api = Admin("https://auth.example.test", "unit", "synthetic-bearer")
            load.assert_called_once_with(api.context)
            self.assertIsNone(api.context.keylog_filename)
            self.assertFalse(path.exists())
            self.assertEqual(ssl.CERT_REQUIRED, api.context.verify_mode)
            self.assertTrue(api.context.check_hostname)
