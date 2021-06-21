from unittest import TestCase
from unittest.mock import patch

from geoip2.errors import AddressNotFoundError

from karrot.utils.geoip import ip_to_city, ip_to_lat_lon, geoip_is_available


@patch('karrot.utils.geoip.geoip')
class TestGeoUtils(TestCase):
    def test_mock_geoip_is_available(self, geoip):
        self.assertTrue(geoip_is_available())

    def test_to_city_swallows_address_not_found_error(self, geoip):
        geoip.city.side_effect = AddressNotFoundError
        self.assertIsNone(ip_to_city('1.2.3.4'))

    def test_to_city_raises_other_errors(self, geoip):
        geoip.city.side_effect = Exception
        with self.assertRaises(Exception):
            ip_to_city('1.2.3.4')

    def test_to_lat_lon_swallows_address_not_found_error(self, geoip):
        geoip.lat_lon.side_effect = AddressNotFoundError
        self.assertIsNone(ip_to_lat_lon('1.2.3.4'))

    def test_to_lat_lon_raises_other_errors(self, geoip):
        geoip.lat_lon.side_effect = Exception
        with self.assertRaises(Exception):
            ip_to_lat_lon('1.2.3.4')
