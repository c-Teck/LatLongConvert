import streamlit as st
import pandas as pd
import time
from io import BytesIO
from datetime import datetime

from api_client import get_client
from utils import (
    get_api_key_from_env,
    load_file,
    find_coordinate_columns,
    validate_coordinates,
    prepare_output_dataframe,
    initialize_processed_data,
    get_error_record,
    get_coordinate_error_record,
    get_rate_limit_record,
    generate_unique_filename,
    validate_coordinate_values,
    calculate_total_processing_time,
    adjust_state_for_known_locations,
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

# Determine available API key (env or manual input)
env_api_key = get_api_key_from_env("default").strip()
manual_api_key = st.sidebar.text_input(
    "🔑 Optional: Enter API key for LocationIQ or Google Maps",
    type="password",
    help="Provide your premium API key to unlock LocationIQ or Google Maps providers",
    key="manual_api_key_input"
).strip()

available_api_key = manual_api_key or env_api_key
has_api_key = bool(available_api_key)

if has_api_key:
    provider_options = ["LocationIQ", "Google Maps", "OpenStreetMap (Nominatim)"]
    default_provider = st.session_state.get("api_provider", provider_options[0])
    if default_provider not in provider_options:
        default_provider = provider_options[0]

    api_provider = st.sidebar.radio(
        "🗺️ Select Geocoding Provider",
        options=provider_options,
        index=provider_options.index(default_provider),
        help="Choose your geocoding service provider"
    )

    if manual_api_key:
        st.sidebar.success("✅ Using manually provided API key")
    else:
        st.sidebar.success("✅ API key loaded from environment")
else:
    api_provider = "OpenStreetMap (Nominatim)"
    st.sidebar.info("ℹ️ No API key detected. Using OpenStreetMap (Nominatim) by default.")
    st.sidebar.warning("⚠️ Free OpenStreetMap usage is limited to approximately 50 calls per hour.")

# Select appropriate API key for chosen provider
if api_provider == "OpenStreetMap (Nominatim)":
    api_key = None
else:
    api_key = available_api_key if has_api_key else None

st.session_state.api_provider = api_provider

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
# MODE SELECTION
# ============================================================================

# Add mode selection tabs
mode_tab1, mode_tab2 = st.tabs(["📁 File Upload Mode", "📍 Direct Input Mode"])

# ============================================================================
# DIRECT INPUT MODE
# ============================================================================

with mode_tab2:
    st.markdown("### 📍 Direct Latitude & Longitude Input")
    st.markdown("Enter up to 10 latitude and longitude pairs to get address and state information.")
    
    # Check if API is configured
    if not st.session_state.api_client:
        st.warning("⚠️ Please configure your API provider and key in the sidebar first")
    else:
        # Number of coordinate pairs
        num_coords = st.number_input(
            "How many coordinate pairs do you want to process?",
            min_value=1,
            max_value=10,
            value=1,
            step=1
        )
        
        st.markdown("---")
        st.markdown("#### 🗺️ Enter Coordinates")
        
        # Create input fields for each coordinate pair
        coords_input = []
        cols = st.columns(2)
        
        for i in range(int(num_coords)):
            st.markdown(f"**Coordinate Pair {i+1}**")
            col1, col2 = st.columns(2)
            
            with col1:
                lat = st.number_input(
                    f"Latitude {i+1}",
                    min_value=-90.0,
                    max_value=90.0,
                    value=0.0,
                    step=0.000001,
                    format="%.6f",
                    key=f"lat_{i}"
                )
            
            with col2:
                lon = st.number_input(
                    f"Longitude {i+1}",
                    min_value=-180.0,
                    max_value=180.0,
                    value=0.0,
                    step=0.000001,
                    format="%.6f",
                    key=f"lon_{i}"
                )
            
            coords_input.append((lat, lon))
        
        st.markdown("---")
        
        # Process button
        if st.button("🚀 Get Addresses", type="primary", use_container_width=True):
            # Validate API client
            if api_provider in ["LocationIQ", "Google Maps"] and not api_key:
                st.error(f"❌ Please enter your {api_provider} API key in the sidebar")
            else:
                # Initialize results storage
                results = []
                
                # Progress indicators
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Process each coordinate
                for idx, (lat, lon) in enumerate(coords_input):
                    status_text.text(f"Processing coordinate {idx + 1} of {num_coords}...")
                    
                    # Validate coordinates
                    is_valid, coord_status = validate_coordinate_values(lat, lon)
                    
                    if not is_valid:
                        results.append({
                            'Pair': idx + 1,
                            'Latitude': lat,
                            'Longitude': lon,
                            'Full Address': 'Invalid Coordinates',
                            'State': 'N/A',
                            'Status': coord_status
                        })
                    else:
                        # Make API call
                        def dummy_log(msg):
                            pass  # Silent logging for direct input
                        
                        result = st.session_state.api_client.reverse_geocode(lat, lon, dummy_log)
                        
                        if result:
                            original_address = result.get('address', 'Not Available')
                            original_state = result.get('state', 'Not Available')
                            corrected_state, corrected_address = adjust_state_for_known_locations(
                                original_address,
                                original_state
                            )
                            results.append({
                                'Pair': idx + 1,
                                'Latitude': lat,
                                'Longitude': lon,
                                'Full Address': corrected_address,
                                'State': corrected_state,
                                'Status': 'Success'
                            })
                        else:
                            results.append({
                                'Pair': idx + 1,
                                'Latitude': lat,
                                'Longitude': lon,
                                'Full Address': 'API Error',
                                'State': 'N/A',
                                'Status': 'Error'
                            })
                        
                        # Rate limiting
                        if idx < num_coords - 1:  # Don't sleep after last request
                            time.sleep(st.session_state.api_client.RATE_LIMIT)
                    
                    # Update progress
                    progress_bar.progress((idx + 1) / num_coords)
                
                # Clear progress indicators
                progress_bar.empty()
                status_text.empty()
                
                # Display results
                st.markdown("---")
                st.markdown("### 📊 Results")
                
                # Create DataFrame
                results_df = pd.DataFrame(results)
                
                # Display success metrics
                success_count = (results_df['Status'] == 'Success').sum()
                error_count = len(results_df) - success_count
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Processed", len(results_df))
                with col2:
                    st.metric("✅ Success", success_count)
                with col3:
                    st.metric("❌ Errors", error_count)
                
                # Show results table with only essential columns
                st.dataframe(
                    results_df[['Latitude', 'Longitude', 'Full Address', 'State']],
                    use_container_width=True,
                    height=400
                )

# ============================================================================
# FILE UPLOAD MODE
# ============================================================================

with mode_tab1:
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

            if remaining_cols:
                id_col = st.selectbox(
                    "Select Unique ID Column",
                    remaining_cols,
                    help="Choose a unique identifier column to track results (e.g., Row ID, Record ID)"
                )
            else:
                st.info("ℹ️ Only latitude and longitude columns detected. Results will omit an ID column.")
                id_col = None

        # Preview data
        st.markdown("### 📋 Data Preview")
        preview_rows = st.slider("Number of rows to preview", 1, min(len(df), 10), 5)
        preview_columns = [col for col in [id_col, lat_col, lon_col] if col]
        st.dataframe(df[preview_columns].head(preview_rows), use_container_width=True)

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

            # Calculate rate limits
            rate_limit = st.session_state.api_client.RATE_LIMIT
            max_requests = 50 if api_provider == "OpenStreetMap (Nominatim)" else None

            if max_requests and valid_coords > max_requests:
                st.warning(
                    f"⚠️ Nominatim free tier allows only {max_requests} lookups per hour. "
                    f"Only the first {max_requests} valid records will be processed; the rest will be marked as rate-limit deferred."
                )

            effective_requests = min(valid_coords, max_requests) if max_requests else valid_coords

            # Calculate total processing time and show countdown
            total_seconds = calculate_total_processing_time(effective_requests, rate_limit)
            
            # Convert to minutes and seconds for display
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            time_display = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
            
            st.info(f"⏱️ **Estimated Processing Time:** {time_display} ({valid_coords} coordinates × {rate_limit}s rate limit)")

            # Create two columns for processing
            log_col, progress_col = st.columns([1, 1])

            with log_col:
                st.markdown("#### 📡 Real-time API Activity Log")
                log_placeholder = st.empty()

            with progress_col:
                st.markdown("#### ⏳ Processing Progress")
                progress_bar = st.progress(0)
                status_text = st.empty()
                countdown_placeholder = st.empty()

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
            skipped_count = 0
            rate_limited_count = 0
            requests_made = 0

            for idx, (i, row) in enumerate(df.iterrows()):
                lat = row[lat_col]
                lon = row[lon_col]

                log_message(f"🔄 Row {idx + 1}/{len(df)}: Processing lat={lat}, lon={lon}")

                # Validate coordinates BEFORE API call
                is_valid, coord_status = validate_coordinate_values(lat, lon)
                
                if not is_valid:
                    # Skip invalid coordinates - no API call made
                    error_record = get_coordinate_error_record(coord_status)
                    processed_data['Latitude'].append(lat)
                    processed_data['Longitude'].append(lon)
                    processed_data['Street1'].append(error_record['Street1'])
                    processed_data['Street2'].append(error_record['Street2'])
                    processed_data['City'].append(error_record['City'])
                    processed_data['State'].append(error_record['State'])
                    processed_data['Postal Code'].append(error_record['Postal Code'])
                    processed_data['Country'].append(error_record['Country'])
                    processed_data['Full Address'].append(error_record['Full Address'])
                    processed_data['Status'].append(error_record['Status'])

                    log_message(f"⏭️ Row {idx + 1} skipped: {coord_status}")
                    skipped_count += 1
                else:
                    if max_requests and requests_made >= max_requests:
                        rate_limit_record = get_rate_limit_record()
                        processed_data['Latitude'].append(lat)
                        processed_data['Longitude'].append(lon)
                        processed_data['Street1'].append(rate_limit_record['Street1'])
                        processed_data['Street2'].append(rate_limit_record['Street2'])
                        processed_data['City'].append(rate_limit_record['City'])
                        processed_data['State'].append(rate_limit_record['State'])
                        processed_data['Postal Code'].append(rate_limit_record['Postal Code'])
                        processed_data['Country'].append(rate_limit_record['Country'])
                        processed_data['Full Address'].append(rate_limit_record['Full Address'])
                        processed_data['Status'].append(rate_limit_record['Status'])

                        rate_limited_count += 1
                        log_message(f"🚫 Row {idx + 1} deferred: hourly limit reached")
                    else:
                        # Valid coordinates - proceed with API call
                        result = st.session_state.api_client.reverse_geocode(lat, lon, log_message)

                        if result:
                            # Success - add result to processed data
                            original_address = result.get('address', '')
                            original_state = result.get('state', '')
                            corrected_state, corrected_address = adjust_state_for_known_locations(
                                original_address,
                                original_state
                            )

                            processed_data['Latitude'].append(lat)
                            processed_data['Longitude'].append(lon)
                            processed_data['Street1'].append(result.get('street1', ''))
                            processed_data['Street2'].append(result.get('street2', ''))
                            processed_data['City'].append(result.get('city', ''))
                            processed_data['State'].append(corrected_state)
                            processed_data['Postal Code'].append(result.get('postal', ''))
                            processed_data['Country'].append(result.get('country', ''))
                            processed_data['Full Address'].append(corrected_address)
                            processed_data['Status'].append('Success')

                            log_message(f"✅ Row {idx + 1} processed successfully")
                            processed_count += 1
                        else:
                            # API Error - add error record
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
                            processed_data['Status'].append(error_record['Status'])

                            log_message(f"❌ Row {idx + 1} failed to process")
                            error_count += 1

                        requests_made += 1

                        # Rate limiting - use client's rate limit
                        time.sleep(st.session_state.api_client.RATE_LIMIT)

                # Update progress with countdown timer
                progress = (idx + 1) / len(df)
                progress_bar.progress(progress)
                
                # Calculate remaining time
                remaining_coords = len(df) - (idx + 1)
                if max_requests:
                    remaining_requests = max(max_requests - requests_made, 0)
                    remaining_coords = min(remaining_coords, remaining_requests)
                remaining_seconds = remaining_coords * rate_limit
                remaining_minutes = remaining_seconds // 60
                remaining_secs = remaining_seconds % 60
                remaining_time = f"{remaining_minutes}m {remaining_secs}s" if remaining_minutes > 0 else f"{remaining_secs}s"
                
                status_text.text(
                    f"Processing: {idx + 1}/{len(df)} rows ({progress * 100:.1f}%) | ✅ {processed_count} Success | ❌ {error_count} Errors | ⏭️ {skipped_count} Skipped | 🚫 {rate_limited_count} Deferred"
                )
                countdown_placeholder.text(f"⏱️ Remaining: {remaining_time}")

            # ====================================================================
            # PROCESSING COMPLETE
            # ====================================================================

            # Create result dataframe
            result_df = prepare_output_dataframe(st.session_state.df, processed_data, id_col, lat_col, lon_col)
            st.session_state.processed_df = result_df

            progress_bar.empty()
            status_text.empty()

            log_message(f"🎉 Geocoding complete!")
            log_message(
                f"📊 Totals — Success: {processed_count} | Errors: {error_count} | Skipped: {skipped_count} | Deferred: {rate_limited_count}"
            )

            st.markdown(
                f'<div class="success-box"><strong>✅ Geocoding Complete!</strong> '
                f'Processed {processed_count} records | {error_count} API errors | {skipped_count} skipped (invalid coordinates) | '
                f'{rate_limited_count} deferred due to hourly cap.</div>',
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
                if id_col:
                    st.markdown(f"**Showing all {len(st.session_state.processed_df)} records with ID column: `{id_col}`**")
                else:
                    st.markdown(
                        f"**Showing all {len(st.session_state.processed_df)} records using columns `{lat_col}` and `{lon_col}` as identifiers**"
                    )
                st.dataframe(st.session_state.processed_df, use_container_width=True, height=400)

            with tab2:
                st.markdown("#### Export Results")

                # Custom filename input (optional)
                st.markdown("**📝 Custom Filename (Optional)**")
                custom_filename = st.text_input(
                    "Enter custom filename",
                    value="",
                    placeholder="Leave empty to auto-generate filename",
                    help="If left empty, a unique filename will be auto-generated"
                )

                # Use custom filename or generate one
                if custom_filename and custom_filename.strip():
                    base_filename = custom_filename.strip()
                else:
                    base_filename = generate_unique_filename()

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
                        file_name=f"{base_filename}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

                with col2:
                    csv_buffer = st.session_state.processed_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download as CSV",
                        data=csv_buffer,
                        file_name=f"{base_filename}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                st.info(f"📌 **Filename:** {base_filename}")

            with tab3:
                st.markdown("#### Data Statistics")
                col1, col2, col3, col4 = st.columns(4)

                total_records = len(st.session_state.processed_df)
                valid_addresses = (st.session_state.processed_df['Geocoding Status'] == 'Success').sum()
                error_records = total_records - valid_addresses
                states_count = st.session_state.processed_df[st.session_state.processed_df['State'] != 'Not Available'][
                    'State'].nunique()
                cities_count = st.session_state.processed_df[st.session_state.processed_df['City'] != 'Not Available'][
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
                    st.session_state.processed_df[st.session_state.processed_df['State'] != 'Not Available']
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
                    st.session_state.processed_df[st.session_state.processed_df['City'] != 'Not Available']
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