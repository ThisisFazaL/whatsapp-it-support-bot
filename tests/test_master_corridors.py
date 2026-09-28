import unittest
from app.services.trip_pricing_service import (
    MASTER_CORRIDORS,
    CITY_MINIMUMS,
    get_corridor,
    get_corridor_by_city,
    get_city_minimum,
    calculate_trip_approval,
    CityNotFoundError
)


class TestMasterCorridors(unittest.TestCase):
    """Verifies all 7 master corridors, 45 delivery stops, and pricing logic."""

    def test_corridor_counts_and_structure(self):
        """Checks that all 7 corridors exist with exact stop counts."""
        self.assertEqual(len(MASTER_CORRIDORS), 7)
        expected_counts = {
            "Corridor 1": 7,
            "Corridor 2": 5,
            "Corridor 3": 8,
            "Corridor 4": 6,
            "Corridor 5": 7,
            "Corridor 6": 11,
            "Corridor 7": 7
        }
        for corridor_key, expected_count in expected_counts.items():
            info = MASTER_CORRIDORS.get(corridor_key)
            self.assertIsNotNone(info, f"Missing {corridor_key}")
            self.assertEqual(
                len(info["stops"]),
                expected_count,
                f"Stop count mismatch for {corridor_key}: expected {expected_count}, got {len(info['stops'])}"
            )

    def test_corridor_5_murambinda_reassignment(self):
        """Verifies Murambinda is in Corridor 5 (East to Mutare and Chipinge), not Masvingo."""
        murambinda_corridor = get_corridor_by_city("Murambinda")
        self.assertIsNotNone(murambinda_corridor)
        self.assertEqual(murambinda_corridor["name"], "East to Mutare and Chipinge")
        self.assertIn("Murambinda", murambinda_corridor["stops"])

        # Also check minimum info
        min_info = get_city_minimum("Murambinda")
        self.assertEqual(min_info["corridor"], "Corridor 5")
        self.assertIn("East to Mutare and Chipinge", min_info["route"])

    def test_all_stops_resolve_to_corridors(self):
        """Verifies every stop across all 7 corridors successfully resolves."""
        for corridor_key, corridor_data in MASTER_CORRIDORS.items():
            for stop in corridor_data["stops"]:
                resolved_corridor = get_corridor_by_city(stop)
                self.assertIsNotNone(
                    resolved_corridor,
                    f"Stop '{stop}' in {corridor_key} did not resolve via get_corridor_by_city."
                )
                self.assertEqual(
                    resolved_corridor["id"],
                    corridor_data["id"],
                    f"Stop '{stop}' resolved to {resolved_corridor['id']} instead of {corridor_data['id']}"
                )

                city_min = get_city_minimum(stop)
                self.assertIsNotNone(city_min)
                self.assertGreater(city_min["required_minimum"], 0.0)

    def test_aliases_and_variants(self):
        """Verifies city aliases like wedza/hwedza, byo, bikita/nyika, jerera/zaka."""
        # Wedza / Hwedza
        w_corr = get_corridor_by_city("wedza")
        hw_corr = get_corridor_by_city("hwedza")
        self.assertEqual(w_corr["id"], "corridor_5")
        self.assertEqual(hw_corr["id"], "corridor_5")

        # Bulawayo / BYO
        byo_corr = get_corridor_by_city("BYO")
        self.assertEqual(byo_corr["id"], "corridor_1")

        # Bikita / Nyika
        bikita_corr = get_corridor_by_city("Bikita")
        self.assertEqual(bikita_corr["id"], "corridor_6")

        # Jerera / Zaka
        jerera_corr = get_corridor_by_city("Jerera")
        self.assertEqual(jerera_corr["id"], "corridor_6")

        # Local variants: Harare, Workington, Msasa, Chitungwiza
        for local_stop in ["Harare", "Workington", "Msasa", "Chitungwiza", "Southerton", "Graniteside"]:
            corr = get_corridor_by_city(local_stop)
            self.assertEqual(corr["id"], "corridor_7")

    def test_get_corridor_lookups(self):
        """Tests lookup by key, number, id, and partial name."""
        self.assertEqual(get_corridor("Corridor 1")["name"], "West to Bulawayo")
        self.assertEqual(get_corridor("1")["name"], "West to Bulawayo")
        self.assertEqual(get_corridor("corridor_1")["name"], "West to Bulawayo")
        self.assertEqual(get_corridor("Bulawayo")["name"], "West to Bulawayo")
        self.assertEqual(get_corridor("7")["name"], "Local / Harare Route")

    def test_trip_approval_and_4_percent_charge(self):
        """Verifies trip approval calculation with 4% shortfall transport charge."""
        # Kadoma minimum = $5,498.44
        # Actual sales = $6,000.00 -> Approved, $0 charge
        res_approved = calculate_trip_approval(6000.00, "Kadoma")
        self.assertTrue(res_approved["approved"])
        self.assertEqual(res_approved["shortfall"], 0.0)
        self.assertEqual(res_approved["transport_charge"], 0.0)
        self.assertEqual(res_approved["corridor"], "Corridor 1")

        # Actual sales = $3,498.44 -> Shortfall = $2,000.00 -> 4% charge = $80.00
        res_deficit = calculate_trip_approval(3498.44, "Kadoma")
        self.assertFalse(res_deficit["approved"])
        self.assertEqual(res_deficit["shortfall"], 2000.0)
        self.assertEqual(res_deficit["transport_charge"], 80.00)
        self.assertEqual(res_deficit["corridor"], "Corridor 1")

    def test_unknown_city_raises_error(self):
        """Verifies unknown destination raises CityNotFoundError."""
        with self.assertRaises(CityNotFoundError):
            get_city_minimum("Atlantis City")


if __name__ == "__main__":
    unittest.main()
