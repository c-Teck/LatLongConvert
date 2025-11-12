import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from typing import Optional, Tuple, Dict, List
from datetime import datetime
import hashlib
import random
import string

# Load environment variables from .env file
load_dotenv()


# ============================================================================
# FILE NAMING & GENERATION
# ============================================================================

def calculate_total_processing_time(valid_coords_count: int, rate_limit: float) -> int:
    """
    Calculate total processing time in seconds.

    Args:
        valid_coords_count: Number of valid coordinates to process
        rate_limit: Rate limit in seconds between requests

    Returns:
        Total time in seconds

    Example:
        >>> total_time = calculate_total_processing_time(50, 1.0)
        >>> print(total_time)
        50  # 50 requests * 1 second
    """
    return int(valid_coords_count * rate_limit)


def generate_unique_filename() -> str:
    """
    Generate a unique filename for geocoded results.

    Format: geocoded_address_timestamp_random_hash

    Returns:
        Unique filename string (without extension)

    Example:
        >>> filename = generate_unique_filename()
        >>> print(filename)
        'geocoded_address_20250101_143022_a7f3b9c2'
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

    filename = f"geocoded_address_{timestamp}_{random_suffix}"

    return filename


# ============================================================================
# ENVIRONMENT & CONFIGURATION
# ============================================================================

def get_api_key_from_env(provider: str) -> Optional[str]:
    """
    Get API key from Streamlit secrets or .env file.

    Priority:
    1. st.secrets (Streamlit Cloud production)
    2. os.getenv (local .env development)

    Args:
        provider: The API provider name (not used but kept for future extensibility)

    Returns:
        API key string if found, empty string otherwise

    Example:
        >>> api_key = get_api_key_from_env("LocationIQ")
        >>> print(api_key)
        'your_api_key_here'
    """
    try:
        # Try Streamlit secrets first (production - Streamlit Cloud)
        if hasattr(st, 'secrets'):
            secret_key = st.secrets.get("MAP_API_KEY", "")
            if secret_key:
                return secret_key
    except FileNotFoundError:
        pass

    # Fall back to dotenv (development - local .env)
    return os.getenv("MAP_API_KEY", "")


# ============================================================================
# FILE HANDLING
# ============================================================================

def load_file(uploaded_file) -> Tuple[pd.DataFrame, List[str], str]:
    """
    Load Excel or CSV file and detect sheets.

    Args:
        uploaded_file: Streamlit UploadedFile object

    Returns:
        Tuple containing:
        - DataFrame: Loaded data
        - List[str]: Sheet names
        - str: Selected sheet name

    Raises:
        ValueError: If file format is not supported

    Example:
        >>> df, sheets, selected = load_file(uploaded_file)
        >>> print(f"Loaded {len(df)} rows from '{selected}'")
    """
    if not uploaded_file:
        raise ValueError("No file uploaded")

    file_extension = uploaded_file.name.split('.')[-1].lower()

    try:
        if file_extension == 'xlsx':
            # Handle Excel files
            excel_file = pd.ExcelFile(uploaded_file)
            sheets = excel_file.sheet_names

            # If multiple sheets, let user select
            if len(sheets) > 1:
                selected_sheet = st.selectbox("📑 Select sheet to process", sheets)
            else:
                selected_sheet = sheets[0]

            df = pd.read_excel(uploaded_file, sheet_name=selected_sheet)

        elif file_extension == 'csv':
            # Handle CSV files
            sheets = ["Sheet1"]
            selected_sheet = "Sheet1"
            df = pd.read_csv(uploaded_file)

        else:
            raise ValueError(f"Unsupported file format: {file_extension}")

        # Validate dataframe
        if df.empty:
            raise ValueError("Uploaded file is empty")

        return df, sheets, selected_sheet

    except Exception as e:
        raise Exception(f"Error loading file: {str(e)}")


# ============================================================================
# COORDINATE COLUMN DETECTION
# ============================================================================

def find_coordinate_columns(df: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
    """
    Automatically detect latitude and longitude columns in dataframe.

    Search priority:
    1. Columns containing "latitude" + "current" (case-insensitive)
    2. Columns containing "longitude" + "current" (case-insensitive)
    3. Generic "latitude" columns
    4. Generic "longitude" columns

    Args:
        df: Input DataFrame

    Returns:
        Tuple of (latitude_column, longitude_column)
        Returns (None, None) if columns not found

    Example:
        >>> df = pd.DataFrame({
        ...     'Current Latitude': [6.5, 9.0],
        ...     'Current Longitude': [3.3, 7.4]
        ... })
        >>> lat, lon = find_coordinate_columns(df)
        >>> print(f"Found: {lat}, {lon}")
        Found: Current Latitude, Current Longitude
    """
    if df.empty or len(df.columns) == 0:
        return None, None

    lat_col = None
    lon_col = None

    # Convert all columns to lowercase for comparison
    columns_lower = {col: col.lower() for col in df.columns}

    # Priority 1: Look for "Current Latitude" and "Current Longitude"
    for col, col_lower in columns_lower.items():
        if "latitude" in col_lower and "current" in col_lower:
            lat_col = col
        if "longitude" in col_lower and "current" in col_lower:
            lon_col = col

    # Priority 2: If not found, look for generic latitude/longitude
    if not lat_col:
        for col, col_lower in columns_lower.items():
            if "latitude" in col_lower:
                lat_col = col
                break

    if not lon_col:
        for col, col_lower in columns_lower.items():
            if "longitude" in col_lower:
                lon_col = col
                break

    return lat_col, lon_col


def get_remaining_columns(df: pd.DataFrame, exclude_cols: List[str]) -> List[str]:
    """
    Get list of remaining columns excluding specified columns.

    Args:
        df: Input DataFrame
        exclude_cols: Column names to exclude

    Returns:
        List of remaining column names

    Example:
        >>> df = pd.DataFrame({
        ...     'Latitude': [6.5],
        ...     'Longitude': [3.3],
        ...     'ID': ['001'],
        ...     'Name': ['John']
        ... })
        >>> remaining = get_remaining_columns(df, ['Latitude', 'Longitude'])
        >>> print(remaining)
        ['ID', 'Name']
    """
    remaining = [col for col in df.columns if col not in exclude_cols]
    return remaining


# ============================================================================
# DATA VALIDATION
# ============================================================================

def validate_coordinates(df: pd.DataFrame, lat_col: str, lon_col: str) -> int:
    """
    Count and validate coordinate pairs in dataframe.

    Args:
        df: Input DataFrame
        lat_col: Latitude column name
        lon_col: Longitude column name

    Returns:
        Count of rows with valid (non-null) coordinate pairs

    Example:
        >>> df = pd.DataFrame({
        ...     'lat': [6.5, None, 9.0],
        ...     'lon': [3.3, 7.4, None]
        ... })
        >>> count = validate_coordinates(df, 'lat', 'lon')
        >>> print(count)
        1  # Only first row has both lat and lon
    """
    if lat_col not in df.columns or lon_col not in df.columns:
        return 0

    # Count rows where both latitude and longitude are not null
    valid_count = df[[lat_col, lon_col]].notna().all(axis=1).sum()

    return int(valid_count)


def validate_coordinate_values(lat: float, lon: float) -> Tuple[bool, str]:
    """
    Validate coordinate values and return status.

    Args:
        lat: Latitude value (-90 to 90)
        lon: Longitude value (-180 to 180)

    Returns:
        Tuple of (is_valid: bool, status: str)
        Status can be: "valid", "no_coordinates", "incomplete_coordinates", "invalid_range"

    Example:
        >>> is_valid, status = validate_coordinate_values(6.5, 3.3)
        >>> print(status)
        'valid'
    """
    try:
        lat_float = float(lat) if pd.notnull(lat) else None
        lon_float = float(lon) if pd.notnull(lon) else None

        # Check if both are missing
        if lat_float is None and lon_float is None:
            return False, "no_coordinates"

        # Check if only one is missing
        if lat_float is None or lon_float is None:
            return False, "incomplete_coordinates"

        # Check if within valid ranges
        if not (-90 <= lat_float <= 90 and -180 <= lon_float <= 180):
            return False, "invalid_range"

        return True, "valid"
    except (ValueError, TypeError):
        return False, "invalid_range"


# ============================================================================
# DATA PROCESSING
# ============================================================================

def initialize_processed_data() -> Dict[str, List]:
    """
    Initialize empty processed data dictionary with all required fields.

    Returns:
        Dictionary with empty lists for all output columns

    Example:
        >>> data = initialize_processed_data()
        >>> data['City'].append('Lagos')
    """
    return {
        'Latitude': [],
        'Longitude': [],
        'Street1': [],
        'Street2': [],
        'City': [],
        'State': [],
        'Postal Code': [],
        'Country': [],
        'Full Address': [],
        'Status': []
    }


def get_error_record() -> Dict[str, str]:
    """
    Get a record with error/placeholder values.

    Returns:
        Dictionary with 'Not Available' values for all address fields

    Example:
        >>> error = get_error_record()
        >>> print(error['City'])
        'Not Available'
    """
    return {
        'Street1': 'Not Available',
        'Street2': 'Not Available',
        'City': 'Not Available',
        'State': 'Not Available',
        'Postal Code': 'Not Available',
        'Country': 'Not Available',
        'Full Address': 'Not Available',
        'Status': 'Error'
    }


def get_coordinate_error_record(error_type: str) -> Dict[str, str]:
    """
    Get error record for coordinate-related issues.

    Args:
        error_type: Type of error - "no_coordinates", "incomplete_coordinates", "invalid_range"

    Returns:
        Dictionary with appropriate error status

    Example:
        >>> error = get_coordinate_error_record("no_coordinates")
        >>> print(error['Status'])
        'No Coordinates Found'
    """
    error_messages = {
        "no_coordinates": "No Coordinates Found",
        "incomplete_coordinates": "Incomplete Coordinates",
        "invalid_range": "Invalid Coordinate Range"
    }

    status = error_messages.get(error_type, "Unknown Error")

    return {
        'Street1': 'Not Available',
        'Street2': 'Not Available',
        'City': 'Not Available',
        'State': 'Not Available',
        'Postal Code': 'Not Available',
        'Country': 'Not Available',
        'Full Address': 'Not Available',
        'Status': status
    }


def get_rate_limit_record() -> Dict[str, str]:
    """
    Get a record representing a rate-limit deferment scenario.

    Returns:
        Dictionary with placeholder values and rate-limit status message.
    """
    return {
        'Street1': 'Not Available',
        'Street2': 'Not Available',
        'City': 'Not Available',
        'State': 'Not Available',
        'Postal Code': 'Not Available',
        'Country': 'Not Available',
        'Full Address': 'Not Available',
        'Status': 'Rate Limit Reached (50/hour cap)'
    }


def prepare_output_dataframe(original_df: pd.DataFrame, processed_data: Dict[str, List],
                             id_col: Optional[str] = None, lat_col: Optional[str] = None,
                             lon_col: Optional[str] = None) -> pd.DataFrame:
    """
    Create formatted output DataFrame with ID | Latitude | Longitude | Geocoding Results.

    Format: ID Column | Latitude | Longitude | Geocoding Results

    Args:
        original_df: Original input DataFrame with all original data
        processed_data: Dictionary with processed geocoding data
        id_col: ID column name to put first in output
        lat_col: Latitude column name from original data
        lon_col: Longitude column name from original data

    Returns:
        Formatted pandas DataFrame with only ID, Lat, Lon, and geocoding results

    Example:
        >>> original_df = pd.DataFrame({'ID': ['001', '002'], 'Latitude': [6.5, 9.0], 'Longitude': [3.3, 7.4]})
        >>> data = initialize_processed_data()
        >>> df = prepare_output_dataframe(original_df, data, 'ID', 'Latitude', 'Longitude')
    """
    # Create result dataframe with geocoding results
    result_df = pd.DataFrame({
        'Street1': processed_data['Street1'],
        'Street2': processed_data['Street2'],
        'City': processed_data['City'],
        'State': processed_data['State'],
        'Postal Code': processed_data['Postal Code'],
        'Country': processed_data['Country'],
        'Full Address': processed_data['Full Address'],
        'Geocoding Status': processed_data['Status']
    })

    # Reset index to ensure alignment
    original_df = original_df.reset_index(drop=True)
    result_df = result_df.reset_index(drop=True)

    # Build final dataframe with only ID, Lat, Lon columns + results
    final_columns = []
    final_data = {}

    if id_col and id_col in original_df.columns:
        final_data[id_col] = original_df[id_col].values

    if lat_col and lat_col in original_df.columns:
        final_data['Latitude'] = pd.to_numeric(original_df[lat_col], errors='coerce').values
    else:
        final_data['Latitude'] = processed_data['Latitude']

    if lon_col and lon_col in original_df.columns:
        final_data['Longitude'] = pd.to_numeric(original_df[lon_col], errors='coerce').values
    else:
        final_data['Longitude'] = processed_data['Longitude']

    # Add geocoding results
    for col in result_df.columns:
        final_data[col] = result_df[col].values

    # Create final dataframe
    final_df = pd.DataFrame(final_data)

    return final_df


# ============================================================================
# DATA STATISTICS & ANALYSIS
# ============================================================================

def calculate_statistics(df: pd.DataFrame) -> Dict[str, any]:
    """
    Calculate statistics from processed geocoding results.

    Args:
        df: Processed results DataFrame

    Returns:
        Dictionary with various statistics

    Example:
        >>> stats = calculate_statistics(df)
        >>> print(f"Success rate: {stats['success_rate']:.1f}%")
    """
    total_records = len(df)
    valid_addresses = (df['Full Address'] != 'Error').sum()
    error_records = total_records - valid_addresses
    success_rate = (valid_addresses / total_records * 100) if total_records > 0 else 0

    # Count unique values (excluding errors)
    states_count = df[df['State'] != 'Error']['State'].nunique()
    cities_count = df[df['City'] != 'Error']['City'].nunique()
    countries_count = df[df['Country'] != 'Error']['Country'].nunique()

    return {
        'total_records': total_records,
        'valid_addresses': valid_addresses,
        'error_records': error_records,
        'success_rate': success_rate,
        'unique_states': states_count,
        'unique_cities': cities_count,
        'unique_countries': countries_count
    }


def get_top_locations(df: pd.DataFrame, column: str, limit: int = 10) -> pd.Series:
    """
    Get top locations by count for a specific column.

    Args:
        df: Results DataFrame
        column: Column name ('State', 'City', 'Country', etc.)
        limit: Number of top results to return

    Returns:
        Pandas Series with top locations and counts (excludes 'Error' values)

    Example:
        >>> top_cities = get_top_locations(df, 'City', limit=5)
        >>> print(top_cities)
    """
    return df[df[column] != 'Error'][column].value_counts().head(limit)


# ============================================================================
# DATA EXPORT & FORMATTING
# ============================================================================

def format_excel_output(df: pd.DataFrame, sheet_name: str = "Geocoded Data") -> bytes:
    """
    Format DataFrame for Excel export with proper formatting.

    Args:
        df: Results DataFrame
        sheet_name: Excel sheet name

    Returns:
        Bytes object suitable for download

    Example:
        >>> excel_bytes = format_excel_output(df)
    """
    from io import BytesIO

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)

    buffer.seek(0)
    return buffer.getvalue()


def format_csv_output(df: pd.DataFrame) -> str:
    """
    Format DataFrame for CSV export.

    Args:
        df: Results DataFrame

    Returns:
        CSV string suitable for download

    Example:
        >>> csv_data = format_csv_output(df)
    """
    return df.to_csv(index=False)


# ============================================================================
# DATA CLEANING & NORMALIZATION
# ============================================================================

def clean_address_field(value: str) -> str:
    """
    Clean and normalize address field values.

    Args:
        value: Raw address field value

    Returns:
        Cleaned value

    Example:
        >>> clean = clean_address_field("  Lagos  ")
        >>> print(f"'{clean}'")
        'Lagos'
    """
    if not isinstance(value, str):
        return ""

    return value.strip()


def adjust_state_for_known_locations(full_address: str, state: str) -> tuple[str, str]:
    """
    Apply manual corrections for known geocoding inaccuracies.
    Corrects both state and full address when a known mismatch is detected.

    Args:
        full_address: The full address returned by the API
        state: The state value returned by the API

    Returns:
        Tuple of (corrected_state, corrected_full_address)
        Returns original values if no correction needed.
    """
    if not isinstance(full_address, str) or not isinstance(state, str):
        return state, full_address

    address_lower = full_address.lower()
    state_lower = state.lower()

    # Check for Lagos-Calabar Coastal Highway / Dangote Refinery with incorrect Delta State
    if (
        "lagos-calabar coastal highway" in address_lower
        and "dangote refinery" in address_lower
        and state_lower == "delta state"
    ):
        corrected_state = "Lagos State"
        # Clean up the full address: remove intermediate location details and replace Delta State with Lagos State
        # Original: "Lagos-Calabar Coastal Highway, Dangote Refinery, Ohoro, Ughelli North, Delta State, 333105, Nigeria"
        # Target: "Lagos-Calabar Coastal Highway, Dangote Refinery, Lagos State, Nigeria"
        
        # Split address by comma and process each part
        parts = [part.strip() for part in full_address.split(',')]
        filtered_parts = []
        
        # Known problematic intermediate locations to remove
        unwanted_locations = ["ohoro", "ughelli north", "ughelli"]
        
        for part in parts:
            part_lower = part.lower()
            
            # Skip unwanted intermediate locations
            if part_lower in unwanted_locations:
                continue
            
            # Replace Delta State with Lagos State
            if part_lower == "delta state":
                filtered_parts.append("Lagos State")
                continue
            
            # Skip postal codes (numeric only parts) to match desired output format
            if part.strip().isdigit():
                continue
            
            # Keep essential parts: Highway, Refinery, State, Country
            if (
                "lagos-calabar coastal highway" in part_lower
                or "dangote refinery" in part_lower
                or "lagos state" in part_lower
                or "nigeria" in part_lower
            ):
                filtered_parts.append(part.strip())
            # Skip other intermediate location parts that aren't essential
            elif not any(keyword in part_lower for keyword in ["highway", "refinery", "state", "nigeria"]):
                # Skip non-essential intermediate locations
                continue
            else:
                filtered_parts.append(part.strip())
        
        # Ensure we have the essential components in order
        # Build final address: Highway, Refinery, State, Country
        final_parts = []
        highway_found = False
        refinery_found = False
        state_found = False
        country_found = False
        
        for part in filtered_parts:
            part_lower = part.lower()
            if "lagos-calabar coastal highway" in part_lower and not highway_found:
                final_parts.append(part)
                highway_found = True
            elif "dangote refinery" in part_lower and not refinery_found:
                final_parts.append(part)
                refinery_found = True
            elif "lagos state" in part_lower and not state_found:
                final_parts.append(part)
                state_found = True
            elif "nigeria" in part_lower and not country_found:
                final_parts.append(part)
                country_found = True
        
        # If we didn't find all parts in filtered_parts, use filtered_parts as-is
        if len(final_parts) < 3:
            final_parts = filtered_parts
        
        corrected_address = ", ".join(final_parts) if final_parts else full_address
        
        return corrected_state, corrected_address

    return state, full_address


def deduplicate_results(df: pd.DataFrame, subset: List[str] = None) -> pd.DataFrame:
    """
    Remove duplicate records from results.

    Args:
        df: Results DataFrame
        subset: Columns to check for duplicates (None = all columns)

    Returns:
        DataFrame with duplicates removed

    Example:
        >>> df_unique = deduplicate_results(df, subset=['Latitude', 'Longitude'])
    """
    if subset is None:
        subset = ['Latitude', 'Longitude', 'Full Address']

    return df.drop_duplicates(subset=subset, keep='first').reset_index(drop=True)