import streamlit as st
import pandas as pd
import requests
import time
import os
from io import BytesIO
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
    .progress-container {
        margin: 1rem 0;
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
    </style>
""", unsafe_allow_html=True)

st.title("🗺️ Geocoding & Address Extraction Dashboard")
st.markdown("Convert latitude/longitude coordinates to detailed addresses with state, city, town, and postal codes")

# Initialize session state
if "df" not in st.session_state:
    st.session_state.df = None
if "processed_df" not in st.session_state:
    st.session_state.processed_df = None
if "sheet_info" not in st.session_state:
    st.session_state.sheet_info = None

# Sidebar configuration
st.sidebar.header("⚙️ Configuration")

api_provider = st.sidebar.radio(
    "🗺️ Select Geocoding Provider",
    options=["Google Maps", "OpenStreetMap (Nominatim)"],
    help="Choose your geocoding service provider"
)

api_key = st.sidebar.text_input(
    "🔑 Enter your API Key",
    type="password",
    help="Your API key for reverse geocoding" if api_provider == "Google Maps" else "Leave empty for OpenStreetMap (free, no key needed)"
)

if api_provider == "Google Maps" and not api_key:
    st.sidebar.warning("⚠️ Google Maps requires an API key")

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
        if api_provider == "Google Maps" and not api_key:
            st.error("❌ Please enter your Google Maps API key in the sidebar")
        else:
            # Validate coordinates
            valid_coords = df[[lat_col, lon_col]].notna().all(axis=1).sum()

            if valid_coords == 0:
                st.error("❌ No valid coordinates found in selected columns")
            else:
                st.success(f"✅ Found {valid_coords} valid coordinate pairs")

                # Process coordinates
                progress_bar = st.progress(0)
                status_text = st.empty()
                results_placeholder = st.empty()

                processed_data = {
                    'Latitude': [],
                    'Longitude': [],
                    'Full Address': [],
                    'State': [],
                    'City': [],
                    'Town': [],
                    'Postal Code': []
                }


                def geocode_nominatim(lat, lon):
                    """Reverse geocode using OpenStreetMap Nominatim"""
                    try:
                        url = f'https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}'
                        headers = {'User-Agent': 'GeoDashboard/1.0'}
                        response = requests.get(url, timeout=10, headers=headers)

                        if response.status_code == 200:
                            data = response.json()
                            address = data.get('display_name', 'Unknown')
                            address_parts = data.get('address', {})

                            return {
                                'address': address,
                                'state': address_parts.get('state', ''),
                                'city': address_parts.get('city', address_parts.get('county', '')),
                                'town': address_parts.get('town', address_parts.get('village', '')),
                                'postal': address_parts.get('postcode', '')
                            }
                    except:
                        pass
                    return None


                def geocode_google_maps(lat, lon, api_key):
                    """Reverse geocode using Google Maps API"""
                    try:
                        url = f'https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}&key={api_key}'
                        response = requests.get(url, timeout=10)

                        if response.status_code == 200:
                            data = response.json()
                            if data.get('results'):
                                result = data['results'][0]
                                address = result.get('formatted_address', 'Unknown')
                                address_components = result.get('address_components', [])

                                # Extract address components
                                state = ''
                                city = ''
                                town = ''
                                postal = ''

                                for component in address_components:
                                    types = component.get('types', [])
                                    long_name = component.get('long_name', '')

                                    if 'administrative_area_level_1' in types:
                                        state = long_name
                                    elif 'locality' in types:
                                        city = long_name
                                    elif 'administrative_area_level_2' in types and not city:
                                        city = long_name
                                    elif 'administrative_area_level_3' in types:
                                        town = long_name
                                    elif 'postal_code' in types:
                                        postal = long_name

                                return {
                                    'address': address,
                                    'state': state,
                                    'city': city,
                                    'town': town,
                                    'postal': postal
                                }
                    except:
                        pass
                    return None


                for idx, (i, row) in enumerate(df.iterrows()):
                    lat = row[lat_col]
                    lon = row[lon_col]

                    if pd.notnull(lat) and pd.notnull(lon):
                        if api_provider == "Google Maps":
                            result = geocode_google_maps(lat, lon, api_key)
                        else:
                            result = geocode_nominatim(lat, lon)

                        if result:
                            processed_data['Latitude'].append(lat)
                            processed_data['Longitude'].append(lon)
                            processed_data['Full Address'].append(result['address'])
                            processed_data['State'].append(result['state'])
                            processed_data['City'].append(result['city'])
                            processed_data['Town'].append(result['town'])
                            processed_data['Postal Code'].append(result['postal'])
                        else:
                            processed_data['Latitude'].append(lat)
                            processed_data['Longitude'].append(lon)
                            processed_data['Full Address'].append('Error')
                            processed_data['State'].append('N/A')
                            processed_data['City'].append('N/A')
                            processed_data['Town'].append('N/A')
                            processed_data['Postal Code'].append('N/A')

                        # Rate limiting (Google Maps allows 50 requests/sec, Nominatim ~1/sec)
                        time.sleep(0.5 if api_provider == "Google Maps" else 1)

                    # Update progress
                    progress = (idx + 1) / valid_coords
                    progress_bar.progress(progress)
                    status_text.text(f"Processing: {idx + 1}/{valid_coords} rows ({progress * 100:.1f}%)")

                # Create result dataframe
                result_df = pd.DataFrame(processed_data)
                st.session_state.processed_df = result_df

                progress_bar.empty()
                status_text.empty()

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
            st.bar_chart(state_counts)

            st.markdown("#### Top Cities")
            city_counts = st.session_state.processed_df['City'].value_counts().head(10)
            st.bar_chart(city_counts)

else:
    st.info("👈 Please upload an Excel or CSV file to get started")
    st.markdown("""
    ### 📋 How to use:
    1. **Upload** your Excel or CSV file using the file uploader in the sidebar
    2. **Configure** your API key in the sidebar (required for geocoding)
    3. **Select** the columns containing latitude and longitude
    4. **Process** the data by clicking the "Start Geocoding" button
    5. **Download** the results as Excel or CSV with extracted location details

    ### ✨ Features:
    - ✅ Supports multiple sheets detection
    - ✅ Automatic column detection for latitude/longitude
    - ✅ Real-time progress tracking
    - ✅ Extracts State, City, Town, and Postal Code
    - ✅ Export results in multiple formats
    - ✅ Built-in statistics and visualization
    """)