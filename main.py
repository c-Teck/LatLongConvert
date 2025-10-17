import streamlit as st
import pandas as pd
import requests
import time
import os
from io import BytesIO
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()


# Function to get API key from secrets or dotenv
def get_api_key():
    try:
        # Try Streamlit secrets first (production)
        return st.secrets.get("MAP_API_KEY", "")
    except FileNotFoundError:
        # Fall back to dotenv (development)
        return os.getenv("MAP_API_KEY", "")


# Page config
st.set_page_config(
    page_title="🗺️ Geocoding Dashboard",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main {
        padding: 2rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeeba;
        color: #856404;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .log-box {
        background-color: #f5f5f5;
        border: 1px solid #ddd;
        color: #333;
        padding: 1rem;
        border-radius: 0.5rem;
        font-family: monospace;
        font-size: 0.85rem;
        max-height: 400px;
        overflow-y: auto;
        margin: 1rem 0;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🗺️ Geocoding & Address Extraction Dashboard")
st.markdown(
    "Convert latitude/longitude coordinates to detailed addresses using LocationIQ, Google Maps, or OpenStreetMap")

# Initialize session state
if "df" not in st.session_state:
    st.session_state.df = None
if "processed_df" not in st.session_state:
    st.session_state.processed_df = None
if "logs" not in st.session_state:
    st.session_state.logs = []

# Sidebar configuration
st.sidebar.header("⚙️ Configuration")

api_provider = st.sidebar.radio(
    "🗺️ Select Geocoding Provider",
    options=["LocationIQ", "Google Maps", "OpenStreetMap (Nominatim)"],
    help="Choose your geocoding service provider"
)

# Get API key from secrets or dotenv
env_api_key = get_api_key()

if api_provider in ["LocationIQ", "Google Maps"]:
    if env_api_key:
        st.sidebar.success(f"✅ {api_provider} API key loaded from environment")
        api_key = env_api_key
    else:
        api_key = st.sidebar.text_input(
            f"🔑 Enter your {api_provider} API Key",
            type="password",
            help=f"Your {api_provider} API key for reverse geocoding"
        )
        if not api_key:
            st.sidebar.warning(f"⚠️ No API key found. Please provide one or add MAP_API_KEY to environment")
else:
    api_key = None
    st.sidebar.info("ℹ️ OpenStreetMap is free and doesn't require an API key")

# File upload
st.sidebar.header("📤 Upload File")
uploaded_file = st.sidebar.file_uploader(
    "Upload Excel or CSV file",
    type=["xlsx", "csv"],
    help="Upload your data file containing latitude and longitude columns"
)

# Main content area
if uploaded_file is not None:
    # Load and analyze file
    if uploaded_file.name.endswith('.xlsx'):
        excel_file = pd.ExcelFile(uploaded_file)
        sheets = excel_file.sheet_names
    else:
        sheets = ["Sheet1"]  # CSV has single sheet

    st.markdown("### 📊 File Analysis")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("📑 Number of Sheets", len(sheets))
    with col2:
        st.metric("📄 File Type", uploaded_file.name.split('.')[-1].upper())

    if len(sheets) > 1:
        st.info(f"ℹ️ Multiple sheets detected: {', '.join(sheets)}")
        selected_sheet = st.selectbox("Select sheet to process", sheets)
    else:
        selected_sheet = sheets[0]
        st.success(f"✅ Single sheet detected: '{selected_sheet}'")

    # Load data from selected sheet
    if uploaded_file.name.endswith('.xlsx'):
        df = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
    else:
        df = pd.read_csv(uploaded_file)

    st.session_state.df = df

    # Display columns
    st.markdown("### 🔍 Available Columns")
    cols_display = st.columns(3)
    with cols_display[0]:
        st.write(f"**Total Columns:** {len(df.columns)}")

    with st.expander("👀 View All Columns"):
        st.write(df.columns.tolist())

    # Find latitude and longitude columns
    lat_col = None
    lon_col = None

    for col in df.columns:
        if "latitude" in col.lower() and "current" in col.lower():
            lat_col = col
        if "longitude" in col.lower() and "current" in col.lower():
            lon_col = col

    # If not found with "Current", try general search
    if not lat_col:
        for col in df.columns:
            if "latitude" in col.lower():
                lat_col = col
                break

    if not lon_col:
        for col in df.columns:
            if "longitude" in col.lower():
                lon_col = col
                break

    st.markdown("### 🎯 Column Selection")

    col1, col2 = st.columns(2)
    with col1:
        lat_col = st.selectbox(
            "Select Latitude Column",
            df.columns,
            index=list(df.columns).index(lat_col) if lat_col in df.columns else 0,
            help="Choose the column containing latitude values"
        )

    with col2:
        lon_col = st.selectbox(
            "Select Longitude Column",
            df.columns,
            index=list(df.columns).index(lon_col) if lon_col in df.columns else 0,
            help="Choose the column containing longitude values"
        )

    # Preview data
    st.markdown("### 📋 Data Preview")
    preview_rows = st.slider("Number of rows to preview", 1, min(len(df), 10), 5)
    st.dataframe(df[[lat_col, lon_col]].head(preview_rows), use_container_width=True)

    # Processing section
    st.markdown("---")
    st.markdown("### ⚡ Process Data")

    if st.button("🚀 Start Geocoding", type="primary", use_container_width=True):
        if api_provider in ["LocationIQ", "Google Maps"] and not api_key:
            st.error(f"❌ Please enter your {api_provider} API key in the sidebar")
        else:
            # Validate coordinates
            valid_coords = df[[lat_col, lon_col]].notna().all(axis=1).sum()

            if valid_coords == 0:
                st.error("❌ No valid coordinates found in selected columns")
            else:
                st.success(f"✅ Found {valid_coords} valid coordinate pairs")

                # Clear logs
                st.session_state.logs = []

                # Create two columns for processing
                log_col, progress_col = st.columns([1, 1])

                with log_col:
                    st.markdown("#### 📡 Real-time API Activity Log")
                    log_placeholder = st.empty()

                with progress_col:
                    st.markdown("#### ⏳ Processing Progress")
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                # Process coordinates
                processed_data = {
                    'Latitude': [],
                    'Longitude': [],
                    'Street1': [],
                    'Street2': [],
                    'City': [],
                    'State': [],
                    'Postal Code': [],
                    'Country': [],
                    'Full Address': []
                }


                def log_message(msg):
                    st.session_state.logs.append(msg)
                    log_placeholder.markdown(f'<div class="log-box">{"<br>".join(st.session_state.logs[-20:])}</div>',
                                             unsafe_allow_html=True)


                def geocode_locationiq(lat, lon, api_key):
                    """Reverse geocode using LocationIQ API"""
                    try:
                        log_message(f"📤 Sending request to LocationIQ: lat={lat}, lon={lon}")
                        url = f'https://us1.locationiq.com/v1/reverse.php?key={api_key}&lat={lat}&lon={lon}&format=json'
                        response = requests.get(url, timeout=10)
                        log_message(f"📥 Response Status: {response.status_code}")

                        if response.status_code == 200:
                            data = response.json()
                            log_message(f"✅ Data received successfully")

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
                            log_message(f"❌ Error: HTTP {response.status_code}")
                    except requests.exceptions.Timeout:
                        log_message(f"⏱️ Request timeout")
                    except Exception as e:
                        log_message(f"❌ Exception: {str(e)}")
                    return None


                def geocode_google_maps(lat, lon, api_key):
                    """Reverse geocode using Google Maps API"""
                    try:
                        log_message(f"📤 Sending request to Google Maps: lat={lat}, lon={lon}")
                        url = f'https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}&key={api_key}'
                        response = requests.get(url, timeout=10)
                        log_message(f"📥 Response Status: {response.status_code}")

                        if response.status_code == 200:
                            data = response.json()
                            if data.get('results'):
                                log_message(f"✅ Data received successfully")
                                result = data['results'][0]
                                address = result.get('formatted_address', '')
                                address_components = result.get('address_components', [])

                                state = ''
                                city = ''
                                postal = ''
                                country = ''

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

                                return {
                                    'street1': address.split(',')[0] if address else '',
                                    'street2': '',
                                    'city': city,
                                    'state': state,
                                    'postal': postal,
                                    'country': country,
                                    'address': address
                                }
                            else:
                                log_message(f"⚠️ No results found")
                        else:
                            log_message(f"❌ Error: HTTP {response.status_code}")
                    except requests.exceptions.Timeout:
                        log_message(f"⏱️ Request timeout")
                    except Exception as e:
                        log_message(f"❌ Exception: {str(e)}")
                    return None


                def geocode_nominatim(lat, lon):
                    """Reverse geocode using OpenStreetMap Nominatim"""
                    try:
                        log_message(f"📤 Sending request to Nominatim: lat={lat}, lon={lon}")
                        url = f'https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}'
                        headers = {'User-Agent': 'GeoDashboard/1.0'}
                        response = requests.get(url, timeout=10, headers=headers)
                        log_message(f"📥 Response Status: {response.status_code}")

                        if response.status_code == 200:
                            data = response.json()
                            log_message(f"✅ Data received successfully")
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
                            log_message(f"❌ Error: HTTP {response.status_code}")
                    except requests.exceptions.Timeout:
                        log_message(f"⏱️ Request timeout")
                    except Exception as e:
                        log_message(f"❌ Exception: {str(e)}")
                    return None


                for idx, (i, row) in enumerate(df.iterrows()):
                    lat = row[lat_col]
                    lon = row[lon_col]

                    log_message(f"🔄 Row {idx + 1}/{valid_coords}: Processing coordinates")

                    if pd.notnull(lat) and pd.notnull(lon):
                        if api_provider == "LocationIQ":
                            result = geocode_locationiq(lat, lon, api_key)
                        elif api_provider == "Google Maps":
                            result = geocode_google_maps(lat, lon, api_key)
                        else:
                            result = geocode_nominatim(lat, lon)

                        if result:
                            processed_data['Latitude'].append(lat)
                            processed_data['Longitude'].append(lon)
                            processed_data['Street1'].append(result['street1'])
                            processed_data['Street2'].append(result['street2'])
                            processed_data['City'].append(result['city'])
                            processed_data['State'].append(result['state'])
                            processed_data['Postal Code'].append(result['postal'])
                            processed_data['Country'].append(result['country'])
                            processed_data['Full Address'].append(result['address'])
                            log_message(f"✅ Row {idx + 1} processed successfully")
                        else:
                            processed_data['Latitude'].append(lat)
                            processed_data['Longitude'].append(lon)
                            processed_data['Street1'].append('Error')
                            processed_data['Street2'].append('Error')
                            processed_data['City'].append('Error')
                            processed_data['State'].append('Error')
                            processed_data['Postal Code'].append('Error')
                            processed_data['Country'].append('Error')
                            processed_data['Full Address'].append('Error')
                            log_message(f"❌ Row {idx + 1} failed to process")

                        # Rate limiting
                        if api_provider == "LocationIQ":
                            time.sleep(0.8)
                        elif api_provider == "Google Maps":
                            time.sleep(0.5)
                        else:
                            time.sleep(1)

                    # Update progress
                    progress = (idx + 1) / valid_coords
                    progress_bar.progress(progress)
                    status_text.text(f"Processing: {idx + 1}/{valid_coords} rows ({progress * 100:.1f}%)")

                # Create result dataframe
                result_df = pd.DataFrame(processed_data)
                st.session_state.processed_df = result_df

                progress_bar.empty()
                status_text.empty()
                log_message("🎉 Geocoding complete!")

                st.markdown(
                    '<div class="success-box"><strong>✅ Geocoding Complete!</strong> All coordinates have been processed.</div>',
                    unsafe_allow_html=True)

    # Display and download results
    if st.session_state.processed_df is not None:
        st.markdown("---")
        st.markdown("### 📊 Results")

        tab1, tab2, tab3 = st.tabs(["📈 Data View", "📥 Download", "📋 Statistics"])

        with tab1:
            st.dataframe(st.session_state.processed_df, use_container_width=True, height=400)

        with tab2:
            col1, col2 = st.columns(2)

            with col1:
                excel_buffer = BytesIO()
                st.session_state.processed_df.to_excel(excel_buffer, index=False, sheet_name="Geocoded Data")
                excel_buffer.seek(0)
                st.download_button(
                    label="📥 Download as Excel",
                    data=excel_buffer,
                    file_name="geocoded_addresses.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            with col2:
                csv_buffer = st.session_state.processed_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download as CSV",
                    data=csv_buffer,
                    file_name="geocoded_addresses.csv",
                    mime="text/csv",
                    use_container_width=True
                )

        with tab3:
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("📍 Total Records", len(st.session_state.processed_df))

            with col2:
                valid_addresses = (st.session_state.processed_df['Full Address'] != 'Error').sum()
                st.metric("✅ Valid Addresses", valid_addresses)

            with col3:
                states = st.session_state.processed_df['State'].nunique()
                st.metric("🏛️ Unique States", states)

            with col4:
                cities = st.session_state.processed_df['City'].nunique()
                st.metric("🏙️ Unique Cities", cities)

            st.markdown("#### Top States")
            state_counts = st.session_state.processed_df['State'].value_counts().head(10)
            if len(state_counts) > 0:
                st.bar_chart(state_counts)

            st.markdown("#### Top Cities")
            city_counts = st.session_state.processed_df['City'].value_counts().head(10)
            if len(city_counts) > 0:
                st.bar_chart(city_counts)

else:
    st.info("👈 Please upload an Excel or CSV file to get started")
    st.markdown("""
    ### 📋 How to use:
    1. **Upload** your Excel or CSV file using the file uploader in the sidebar
    2. **Configure** your API key in the sidebar (or use MAP_API_KEY from environment)
    3. **Select** the columns containing latitude and longitude
    4. **Process** the data by clicking the "Start Geocoding" button
    5. **Monitor** real-time API activity in the log panel
    6. **Download** the results as Excel or CSV with extracted location details

    ### 🗺️ Supported APIs:
    - **LocationIQ** - High accuracy, structured address data
    - **Google Maps** - Comprehensive coverage, detailed components
    - **OpenStreetMap (Nominatim)** - Free option, no API key needed

    ### 📊 Output Columns:
    - Latitude & Longitude (original coordinates)
    - Street1 (house number + road)
    - Street2 (quarter + suburb)
    - City
    - State
    - Postal Code
    - Country
    - Full Address

    ### ⚙️ Environment Setup:
    Add to your `.env` file or Streamlit secrets:
    ```
    MAP_API_KEY=your_api_key_here
    ```
    """)