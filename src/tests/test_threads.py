import unittest
from src.daq import mccdaq


class TestGetBathTemp(unittest.TestCase):

    def setUp(self):
        self.daq = mccdaq.Daq()
        self.daq.set_starting_temp(self.init_temp)

    def test_default_values(self):
        """
        Test the function with the default values
        """
        bath_temp = self.daq.get_bath_temp()
        self.assertIsInstance(bath_temp, float)
        # Any additional test for the output of the function

    def test_custom_values(self):
        """
        Test the function with custom values
        """
        bath_temp = self.daq.get_bath_temp(samples=50, interval=2)
        self.assertIsInstance(bath_temp, float)
        # Any additional test for the output of the function

    def test_edge_cases(self):
        """
        Test the function with edge cases
        """
        bath_temp = self.daq.get_bath_temp(samples=-1, interval=-1)
        self.assertEqual(bath_temp, None)

        bath_temp = self.daq.get_bath_temp(samples=0, interval=0)
        self.assertEqual(bath_temp, None)

        bath_temp = self.daq.get_bath_temp(samples=0, interval=10)
        self.assertEqual(bath_temp, None)
        # Any additional test for the edge cases that make sense


if __name__ == '__main__':
    unittest.main()