import sys
import tempfile
import unittest
from pathlib import Path
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from notta_to_knowledge import parse_xlsx


class NottaExportTests(unittest.TestCase):
    def test_export_preamble_is_not_ingested_and_times_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.xlsx'
            wb = Workbook()
            for row in [('動画タイトル',), ('火曜日 2026.10.27',), ('AI Notes',),
                        ('00:02', '未設定話者', '本文'), ('01:02:03', '話者1', '続き')]:
                wb.active.append(row)
            wb.save(path)
            cues, warnings = parse_xlsx(path)
            self.assertEqual([c.start_sec for c in cues], [2, 3723])
            self.assertEqual([c.text for c in cues], ['本文', '続き'])
            self.assertEqual(warnings, [])


if __name__ == '__main__':
    unittest.main()
