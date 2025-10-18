import streamlit as st
import pandas as pd
import time
from io import BytesIO

from api_client import get_client
from utils import (
    get_api_key_from_env,
    load_file,
    find_coordinate_columns,
    validate_coordinates,
    prepare_output_dataframe,
    initialize_processed_data,
    get_error_record
)

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

# ============================================================================
# PAGE SETUP
# ============================================================================

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
if "api_client" not in st.session_state:
    st.session_state.api_client = None
if "api_provider" not in st.session_state:
    st.session_state.api_provider = None

# ============================================================================
# SIDEBAR CONFIGURATION
# ============================================================================

st.sidebar.header("⚙️ Configuration")

api_provider = st.sidebar.radio(
    "🗺️ Select Geocoding Provider",
    options=["LocationIQ", "Google Maps", "OpenStreetMap (Nominatim)"],
    help="Choose your geocoding service provider"
)

st.session_state.api_provider = api_provider

# Get API key from environment
env_api_key = get_api_key_from_env(api_provider)

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

# Initialize API client
try:
    if api_key or api_provider == "OpenStreetMap (Nominatim)":
        st.session_state.api_client = get_client(api_provider, api_key)
except Exception as e:
    st.sidebar.error(f"❌ Failed to initialize API client: {str(e)}")

# File upload
st.sidebar.header("📤 Upload File")
uploaded_file = st.sidebar.file_uploader(
    "Upload Excel or CSV file",
    type=["xlsx", "csv"],
    help="Upload your data file containing latitude and longitude columns"
)

# ============================================================================
# MAIN CONTENT AREA
# ============================================================================

if uploaded_file is not None:
    # Load file
    try:
        df, sheets, selected_sheet = load_file(uploaded_file)
        st.session_state.df = df
    except Exception as e:
        st.error(f"❌ Error loading file: {str(e)}")
        st.stop()

    # File analysis
    st.markdown("### 📊 File Analysis")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("📑 Number of Sheets", len(sheets))
    with col2:
        st.metric("📄 File Type", uploaded_file.name.split('.')[-1].upper())

    if len(sheets) > 1:
        st.info(f"ℹ️ Multiple sheets detected: {', '.join(sheets)}")
    else:
        st.success(f"✅ Single sheet detected: '{selected_sheet}'")

    # Display columns
    st.markdown("### 🔍 Available Columns")
    st.write(f"**Total Columns:** {len(df.columns)}")

    with st.expander("👀 View All Columns"):
        st.write(df.columns.tolist())

    # Find and select coordinate columns
    lat_col, lon_col = find_coordinate_columns(df)

    st.markdown("### 🎯 Column Selection")

    col1, col2, col3 = st.columns(3)
    with col1:
        lat_col = st.selectbox(
            "Select Latitude Column",
            df.columns,
            index=list(df.columns).index(lat_col) if lat_col and lat_col in df.columns else 0,
            help="Choose the column containing latitude values"
        )

    with col2:
        lon_col = st.selectbox(
            "Select Longitude Column",
            df.columns,
            index=list(df.columns).index(lon_col) if lon_col and lon_col in df.columns else 0,
            help="Choose the column containing longitude values"
        )

    with col3:
        # Get remaining columns (excluding lat and lon)
        remaining_cols = [col for col in df.columns if col not in [lat_col, lon_col]]

        id_col = st.selectbox(
            "Select Unique ID Column",
            remaining_cols,
            help="Choose a unique identifier column to track results (e.g., Row ID, Record ID)"
        )

    # Preview data
    st.markdown("### 📋 Data Preview")
    preview_rows = st.slider("Number of rows to preview", 1, min(len(df), 10), 5)
    st.dataframe(df[[lat_col, lon_col]].head(preview_rows), use_container_width=True)

    # ========================================================================
    # PROCESSING SECTION
    # ========================================================================

    st.markdown("---")
    st.markdown("### ⚡ Process Data")

    if st.button("🚀 Start Geocoding", type="primary", use_container_width=True):
        # Validate before processing
        if api_provider in ["LocationIQ", "Google Maps"] and not api_key:
            st.error(f"❌ Please enter your {api_provider} API key in the sidebar")
            st.stop()

        if not st.session_state.api_client:
            st.error("❌ API client not initialized. Please check your configuration.")
            st.stop()

        # Validate coordinates
        valid_coords = validate_coordinates(df, lat_col, lon_col)

        if valid_coords == 0:
            st.error("❌ No valid coordinates found in selected columns")
            st.stop()

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

        # Initialize processed data
        processed_data = initialize_processed_data()


        def log_message(msg):
            """Add message to logs and update display"""
            st.session_state.logs.append(msg)
            log_placeholder.markdown(
                f'<div class="log-box">{"<br>".join(st.session_state.logs[-20:])}</div>',
                unsafe_allow_html=True
            )


        # ====================================================================
        # MAIN PROCESSING LOOP
        # ====================================================================

        log_message(f"🚀 Starting geocoding with {api_provider}")
        log_message(f"📊 Processing {valid_coords} coordinates...")

        processed_count = 0
        error_count = 0

        for idx, (i, row) in enumerate(df.iterrows()):
            lat = row[lat_col]
            lon = row[lon_col]

            log_message(f"🔄 Row {idx + 1}/{len(df)}: Processing lat={lat}, lon={lon}")

            if pd.notnull(lat) and pd.notnull(lon):
                # Use API client to reverse geocode
                result = st.session_state.api_client.reverse_geocode(lat, lon, log_message)

                if result:
                    # Success - add result to processed data
                    processed_data['Latitude'].append(lat)
                    processed_data['Longitude'].append(lon)
                    processed_data['Street1'].append(result.get('street1', ''))
                    processed_data['Street2'].append(result.get('street2', ''))
                    processed_data['City'].append(result.get('city', ''))
                    processed_data['State'].append(result.get('state', ''))
                    processed_data['Postal Code'].append(result.get('postal', ''))
                    processed_data['Country'].append(result.get('country', ''))
                    processed_data['Full Address'].append(result.get('address', ''))

                    log_message(f"✅ Row {idx + 1} processed successfully")
                    processed_count += 1
                else:
                    # Error - add error record
                    error_record = get_error_record()
                    processed_data['Latitude'].append(lat)
                    processed_data['Longitude'].append(lon)
                    processed_data['Street1'].append(error_record['Street1'])
                    processed_data['Street2'].append(error_record['Street2'])
                    processed_data['City'].append(error_record['City'])
                    processed_data['State'].append(error_record['State'])
                    processed_data['Postal Code'].append(error_record['Postal Code'])
                    processed_data['Country'].append(error_record['Country'])
                    processed_data['Full Address'].append(error_record['Full Address'])

                    log_message(f"❌ Row {idx + 1} failed to process")
                    error_count += 1

                # Rate limiting - use client's rate limit
                time.sleep(st.session_state.api_client.RATE_LIMIT)

            # Update progress
            progress = (idx + 1) / len(df)
            progress_bar.progress(progress)
            status_text.text(
                f"Processing: {idx + 1}/{len(df)} rows ({progress * 100:.1f}%) | ✅ {processed_count} Success | ❌ {error_count} Errors"
            )

        # ====================================================================
        # PROCESSING COMPLETE
        # ====================================================================

        # Create result dataframe
        result_df = prepare_output_dataframe(processed_data)
        st.session_state.processed_df = result_df

        progress_bar.empty()
        status_text.empty()

        log_message(f"🎉 Geocoding complete!")
        log_message(f"📊 Total Processed: {processed_count} | Errors: {error_count}")

        st.markdown(
            f'<div class="success-box"><strong>✅ Geocoding Complete!</strong> '
            f'Processed {processed_count} records with {error_count} errors.</div>',
            unsafe_allow_html=True
        )

    # ========================================================================
    # DISPLAY RESULTS
    # ========================================================================

    if st.session_state.processed_df is not None:
        st.markdown("---")
        st.markdown("### 📊 Results")

        tab1, tab2, tab3 = st.tabs(["📈 Data View", "📥 Download", "📋 Statistics"])

        with tab1:
            st.markdown("#### Complete Geocoded Data")
            st.dataframe(st.session_state.processed_df, use_container_width=True, height=400)

        with tab2:
            st.markdown("#### Export Results")
            col1, col2 = st.columns(2)

            with col1:
                excel_buffer = BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    st.session_state.processed_df.to_excel(
                        writer,
                        index=False,
                        sheet_name="Geocoded Data"
                    )
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
            st.markdown("#### Data Statistics")
            col1, col2, col3, col4 = st.columns(4)

            total_records = len(st.session_state.processed_df)
            valid_addresses = (st.session_state.processed_df['Full Address'] != 'Error').sum()
            error_records = total_records - valid_addresses
            states_count = st.session_state.processed_df[st.session_state.processed_df['State'] != 'Error'][
                'State'].nunique()
            cities_count = st.session_state.processed_df[st.session_state.processed_df['City'] != 'Error'][
                'City'].nunique()

            with col1:
                st.metric("📍 Total Records", total_records)
            with col2:
                st.metric("✅ Valid Addresses", valid_addresses)
            with col3:
                st.metric("❌ Errors", error_records)
            with col4:
                success_rate = (valid_addresses / total_records * 100) if total_records > 0 else 0
                st.metric("🎯 Success Rate", f"{success_rate:.1f}%")

            st.markdown("#### Top States")
            state_counts = (
                st.session_state.processed_df[st.session_state.processed_df['State'] != 'Error']
                ['State']
                .value_counts()
                .head(10)
            )
            if len(state_counts) > 0:
                st.bar_chart(state_counts)
            else:
                st.info("No state data available")

            st.markdown("#### Top Cities")
            city_counts = (
                st.session_state.processed_df[st.session_state.processed_df['City'] != 'Error']
                ['City']
                .value_counts()
                .head(10)
            )
            if len(city_counts) > 0:
                st.bar_chart(city_counts)
            else:
                st.info("No city data available")

else:
    st.info("👈 Please upload an Excel or CSV file to get started")
    st.markdown("""
    ### 📋 How to use:
    1. **Upload** your Excel or CSV file using the file uploader in the sidebar
    2. **Configure** your API provider and key in the sidebar
    3. **Select** the columns containing latitude and longitude
    4. **Process** the data by clicking the "Start Geocoding" button
    5. **Monitor** real-time API activity in the log panel
    6. **Download** the results as Excel or CSV with extracted location details

    ### 🗺️ Supported APIs:
    - **LocationIQ** - High accuracy, structured address data
    - **Google Maps** - Comprehensive coverage, detailed components
    - **OpenStreetMap (Nominatim)** - Free option, no API key needed

    ### 📊 Output Columns:
    - **Latitude & Longitude** - Original coordinates
    - **Street1** - House number + road
    - **Street2** - Quarter + suburb
    - **City** - City name
    - **State** - State/province name
    - **Postal Code** - Postal/zip code
    - **Country** - Country name
    - **Full Address** - Complete formatted address

    ### ⚙️ Environment Setup:
    Create a `.env` file in your project root:
    ```
    MAP_API_KEY=your_api_key_here
    ```

    Or add to Streamlit Cloud secrets:
    ```
    MAP_API_KEY = "your_api_key_here"
    ```
    """)