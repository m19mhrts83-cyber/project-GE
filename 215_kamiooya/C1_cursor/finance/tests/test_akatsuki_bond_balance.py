import unittest

from akatsuki_bond_balance import _extract_amounts_from_tables


class TestAkatsukiBondParser(unittest.TestCase):
    def test_extract_by_amount_header_column(self):
        tables = [
            {
                "headers": ["商品", "評価額", "償還日"],
                "rows": [
                    ["国内債券A", "1,234,000円", "2029/01/01"],
                    ["外国債券B", "2,000,000円", "2031/06/30"],
                ],
            }
        ]
        amounts, mode = _extract_amounts_from_tables(tables)
        self.assertEqual(mode, "header-column")
        self.assertEqual(amounts, [1234000, 2000000])

    def test_extract_row_fallback_when_no_header(self):
        tables = [
            {
                "headers": ["商品", "数量", "償還日"],
                "rows": [
                    ["国内債券A", "100", "2029/01/01"],
                    ["外国債券B 残高 3,210,000円", "-", "-"],
                ],
            }
        ]
        amounts, mode = _extract_amounts_from_tables(tables)
        self.assertEqual(mode, "row-max-fallback")
        self.assertEqual(amounts, [3210000])


if __name__ == "__main__":
    unittest.main()
