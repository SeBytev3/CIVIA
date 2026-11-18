import ipaddress
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from lan import civia_lan


class LanContractTests(unittest.TestCase):
    def test_pairing_contains_only_public_information_and_encoded_https_origin(self):
        installation = uuid.UUID("0b647947-70be-4fa1-b6a1-a221e236dfce")
        result = civia_lan.pairing_uri(installation, "192.168.1.4", 5443, "cb" * 32)
        self.assertEqual(
            result,
            f"civia://pair?v=1&id={installation}&origin=https%3A%2F%2F192.168.1.4%3A5443&pin={'cb' * 32}",
        )

    def test_lan_is_limited_to_rfc1918_unicast_addresses(self):
        for address in ("127.0.0.1", "0.0.0.0", "172.32.0.4", "169.254.1.2", "224.0.0.251", "::1", "203.0.113.1"):
            with self.subTest(address=address), self.assertRaises(ValueError):
                civia_lan.private_address(address)
        self.assertEqual(civia_lan.private_address("172.28.0.10"), ipaddress.IPv4Address("172.28.0.10"))

    def test_discovery_probe_requires_healthy_gateway_and_installation_identity(self):
        installation = uuid.UUID("0b647947-70be-4fa1-b6a1-a221e236dfce")
        with patch.object(civia_lan, "https_json") as get:
            get.side_effect = [{"status": "ok"}, {"protocol": 1, "installation_id": str(installation)}]
            self.assertTrue(civia_lan.healthy("192.168.1.4", 5443, "civia.local", Path("ca"), installation))
            get.side_effect = [{"status": "ok"}, {"protocol": 1, "installation_id": str(uuid.uuid4())}]
            self.assertFalse(civia_lan.healthy("192.168.1.4", 5443, "civia.local", Path("ca"), installation))

    def test_metadata_is_parsed_and_requires_matching_protocol(self):
        with self.assertRaises(ValueError):
            civia_lan.installation_id(json.loads('{"protocol": 2, "installation_id": "bad"}'))


if __name__ == "__main__":
    unittest.main()
