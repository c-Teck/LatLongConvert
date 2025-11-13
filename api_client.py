import requests
import time
from typing import Optional, Dict, Callable


class GeocodingAPIClient:
    """Base class for geocoding API clients"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.timeout = 10

    def reverse_geocode(self, lat: float, lon: float, log_callback: Callable) -> Optional[Dict]:
        """Reverse geocode coordinates. Must be implemented by subclasses"""
        raise NotImplementedError


class LocationIQClient(GeocodingAPIClient):
    """LocationIQ API Client for reverse geocoding"""

    BASE_URL = "https://us1.locationiq.com/v1/reverse.php"
    RATE_LIMIT = 0.9  # seconds

    def reverse_geocode(self, lat: float, lon: float, log_callback: Callable) -> Optional[Dict]:
        """Reverse geocode using LocationIQ API"""
        try:
            log_callback(f"📤 Sending request to LocationIQ: lat={lat}, lon={lon}")

            url = f"{self.BASE_URL}?key={self.api_key}&lat={lat}&lon={lon}&format=json"
            response = requests.get(url, timeout=self.timeout)

            log_callback(f"📥 Response Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                log_callback(f"✅ Data received successfully")

                address = data.get('address', {})
                house_number = address.get('house_number', '')
                road = address.get('road', '')
                quarter = address.get('quarter', '')
                suburb = address.get('suburb', '')
                city = address.get('city', '')
                state = address.get('state', '')
                postcode = address.get('postcode', '')
                country = address.get('country', '')
                display_name = data.get('display_name', '')

                street1 = f"{house_number} {road}".strip()
                street2 = f"{quarter} {suburb}".strip()

                return {
                    'street1': street1,
                    'street2': street2,
                    'city': city,
                    'state': state,
                    'postal': postcode,
                    'country': country,
                    'address': display_name
                }
            else:
                log_callback(f"❌ Error: HTTP {response.status_code}")

        except requests.exceptions.Timeout:
            log_callback(f"⏱️ Request timeout")
        except requests.exceptions.RequestException as e:
            log_callback(f"❌ Request failed: {str(e)}")
        except Exception as e:
            log_callback(f"❌ Exception: {str(e)}")

        return None


class GoogleMapsClient(GeocodingAPIClient):
    """Google Maps API Client for reverse geocoding"""

    BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    RATE_LIMIT = 0.5  # seconds

    def reverse_geocode(self, lat: float, lon: float, log_callback: Callable) -> Optional[Dict]:
        """Reverse geocode using Google Maps API"""
        try:
            log_callback(f"📤 Sending request to Google Maps: lat={lat}, lon={lon}")

            url = f"{self.BASE_URL}?latlng={lat},{lon}&key={self.api_key}"
            response = requests.get(url, timeout=self.timeout)

            log_callback(f"📥 Response Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()

                if data.get('results'):
                    log_callback(f"✅ Data received successfully")
                    
                    # Filter out plus code results and prefer proper addresses
                    results = data['results']
                    preferred_result = None
                    
                    # Priority order for result types (prefer detailed addresses over plus codes)
                    preferred_types = [
                        'street_address',
                        'premise',
                        'subpremise',
                        'route',
                        'intersection',
                        'political',
                        'locality',
                        'administrative_area_level_1',
                        'administrative_area_level_2',
                        'administrative_area_level_3',
                        'administrative_area_level_4',
                        'administrative_area_level_5'
                    ]
                    
                    # First, try to find a result that's NOT a plus code and has preferred types
                    for result in results:
                        result_types = result.get('types', [])
                        # Skip plus codes
                        if 'plus_code' in result_types:
                            continue
                        # Prefer results with street addresses or routes
                        if any(pref_type in result_types for pref_type in preferred_types):
                            preferred_result = result
                            break
                    
                    # If no preferred result found, use first non-plus-code result
                    if not preferred_result:
                        for result in results:
                            result_types = result.get('types', [])
                            if 'plus_code' not in result_types:
                                preferred_result = result
                                break
                    
                    # Fallback to first result if all are plus codes (shouldn't happen, but just in case)
                    if not preferred_result:
                        preferred_result = results[0]
                        log_callback(f"⚠️ Only plus code available, using it as fallback")
                    
                    address = preferred_result.get('formatted_address', '')
                    address_components = preferred_result.get('address_components', [])

                    state = ''
                    city = ''
                    postal = ''
                    country = ''
                    street_number = ''
                    route = ''

                    for component in address_components:
                        types = component.get('types', [])
                        long_name = component.get('long_name', '')

                        if 'administrative_area_level_1' in types:
                            state = long_name
                        elif 'locality' in types:
                            city = long_name
                        elif 'postal_code' in types:
                            postal = long_name
                        elif 'country' in types:
                            country = long_name
                        elif 'street_number' in types:
                            street_number = long_name
                        elif 'route' in types:
                            route = long_name

                    # Build street1 from street number and route
                    street1 = f"{street_number} {route}".strip()
                    if not street1 and address:
                        # Fallback to first part of formatted address
                        street1 = address.split(',')[0] if address else ''

                    return {
                        'street1': street1,
                        'street2': '',
                        'city': city,
                        'state': state,
                        'postal': postal,
                        'country': country,
                        'address': address
                    }
                else:
                    log_callback(f"⚠️ No results found")
            else:
                log_callback(f"❌ Error: HTTP {response.status_code}")

        except requests.exceptions.Timeout:
            log_callback(f"⏱️ Request timeout")
        except requests.exceptions.RequestException as e:
            log_callback(f"❌ Request failed: {str(e)}")
        except Exception as e:
            log_callback(f"❌ Exception: {str(e)}")

        return None


class NominatimClient(GeocodingAPIClient):
    """OpenStreetMap Nominatim API Client for reverse geocoding"""

    BASE_URL = "https://nominatim.openstreetmap.org/reverse"
    RATE_LIMIT = 1.0  # seconds

    def reverse_geocode(self, lat: float, lon: float, log_callback: Callable) -> Optional[Dict]:
        """Reverse geocode using OpenStreetMap Nominatim API"""
        try:
            log_callback(f"📤 Sending request to Nominatim: lat={lat}, lon={lon}")

            url = f"{self.BASE_URL}?format=json&lat={lat}&lon={lon}"
            headers = {'User-Agent': 'GeoDashboard/1.0'}
            response = requests.get(url, timeout=self.timeout, headers=headers)

            log_callback(f"📥 Response Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                log_callback(f"✅ Data received successfully")

                address = data.get('display_name', '')
                address_parts = data.get('address', {})

                return {
                    'street1': address_parts.get('road', ''),
                    'street2': address_parts.get('suburb', ''),
                    'city': address_parts.get('city', address_parts.get('county', '')),
                    'state': address_parts.get('state', ''),
                    'postal': address_parts.get('postcode', ''),
                    'country': address_parts.get('country', ''),
                    'address': address
                }
            else:
                log_callback(f"❌ Error: HTTP {response.status_code}")

        except requests.exceptions.Timeout:
            log_callback(f"⏱️ Request timeout")
        except requests.exceptions.RequestException as e:
            log_callback(f"❌ Request failed: {str(e)}")
        except Exception as e:
            log_callback(f"❌ Exception: {str(e)}")

        return None


def get_client(provider: str, api_key: Optional[str] = None) -> GeocodingAPIClient:
    """Factory function to get the appropriate API client"""
    if provider == "LocationIQ":
        return LocationIQClient(api_key)
    elif provider == "Google Maps":
        return GoogleMapsClient(api_key)
    elif provider == "OpenStreetMap (Nominatim)":
        return NominatimClient(api_key)
    else:
        raise ValueError(f"Unknown provider: {provider}")