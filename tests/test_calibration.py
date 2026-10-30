import unittest
from src.calibration import calibrate


class CalibrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_per_tool_samples(self):
        result = await calibrate(['search', 'read_document', 'lookup_rows', 'calculate'], .005)
        self.assertEqual(set(result), {'search', 'read_document', 'lookup_rows', 'calculate'})
        self.assertTrue(all(len(samples) == 3 for samples in result.values()))
        self.assertTrue(all(value >= .005 for samples in result.values() for value in samples))

    async def test_rejects_too_few(self):
        with self.assertRaises(ValueError):
            await calibrate(['search'], .005, repeats=2)
