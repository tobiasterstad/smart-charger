import unittest

from smart_charger.zaptec import OperatingMode


class TestOperatingModeFromName(unittest.TestCase):

    def test_exact_name(self):
        self.assertEqual(OperatingMode.from_name('Connected_Charging'), OperatingMode.Connected_Charging)

    def test_lowercase_with_spaces(self):
        self.assertEqual(OperatingMode.from_name('connected charging'), OperatingMode.Connected_Charging)

    def test_mixed_with_dashes_and_underscores(self):
        self.assertEqual(OperatingMode.from_name('Connected-Charging'), OperatingMode.Connected_Charging)
        self.assertEqual(OperatingMode.from_name('connected_charging'), OperatingMode.Connected_Charging)
        self.assertEqual(OperatingMode.from_name('connected.charging'), OperatingMode.Connected_Charging)

    def test_numeric_string(self):
        self.assertEqual(OperatingMode.from_name('3'), OperatingMode.Connected_Charging)
        self.assertEqual(OperatingMode.from_name('0'), OperatingMode.Unknown)

    def test_substring_matches(self):
        # Should match by substring fallback
        self.assertEqual(OperatingMode.from_name('charging'), OperatingMode.Connected_Charging)
        self.assertEqual(OperatingMode.from_name('requesting'), OperatingMode.Connected_Requesting)

    def test_none_or_empty(self):
        self.assertEqual(OperatingMode.from_name(None), OperatingMode.Unknown)
        self.assertEqual(OperatingMode.from_name(''), OperatingMode.Unknown)

    def test_unknown_string(self):
        self.assertEqual(OperatingMode.from_name('unrelated_mode'), OperatingMode.Unknown)


if __name__ == '__main__':
    unittest.main()
