import streamlit as st
import requests
import json
import os
import pandas as pd
from notion_client import Client
import plotly.graph_objects as go
from datetime import datetime


# Set page configuration
st.set_page_config(
    page_title="TrueClaim Manager",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
        .main {
            padding: 2rem;
        }
        .stButton>button {
            width: 100%;
            border-radius: 5px;
            height: 3em;
            background-color: #FF4B4B;
            color: white;
            font-weight: bold;
        }
        .stButton>button:hover {
            background-color: #FF2B2B;
        }
        div[data-testid="stMetricValue"] {
            font-size: 28px;
            color: #FF4B4B;
        }
        .status-card {
            padding: 1rem;
            border-radius: 5px;
            background-color: #f0f2f6;
            margin-bottom: 1rem;
        }
        .chart-container {
            background-color: white;
            padding: 1rem;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .sidebar .sidebar-content {
            background-color: #f0f2f6;
        }
        h1 {
            color: #FF4B4B;
            font-weight: bold;
            margin-bottom: 2rem;
        }
        h2 {
            color: #31333F;
            margin-top: 2rem;
        }
        .stProgress > div > div > div > div {
            background-color: #FF4B4B;
        }
        /* Sidebar styling */
        section[data-testid="stSidebar"] > div {
            background-color: #f8f9fa;
            padding: 2rem 1rem;
        }
        .sidebar-title {
            text-align: center;
            color: #FF4B4B;
            font-size: 1.5em;
            font-weight: bold;
            margin-bottom: 0.5rem;
            padding: 1rem 0;
            border-bottom: 2px solid #FF4B4B;
        }
        .sidebar-subtitle {
            text-align: center;
            color: #666;
            font-size: 0.9em;
            margin-bottom: 2rem;
        }
        .nav-link {
            padding: 0.5rem 1rem;
            margin: 0.5rem 0;
            border-radius: 5px;
            cursor: pointer;
            transition: background-color 0.3s;
        }
        .nav-link:hover {
            background-color: #FF4B4B20;
        }
        .nav-link.active {
            background-color: #FF4B4B;
            color: white;
        }
        .sidebar-footer {
            position: fixed;
            bottom: 0;
            left: 0;
            width: 100%;
            padding: 1rem;
            background-color: #f8f9fa;
            border-top: 1px solid #eee;
            text-align: center;
            font-size: 0.8em;
            color: #666;
        }
        /* Radio button styling */
        div[role="radiogroup"] label {
            padding: 0.5rem 1rem;
            margin: 0.5rem 0;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
        }
        div[role="radiogroup"] label:hover {
            background-color: #FF4B4B20;
        }
        div[role="radiogroup"] label input:checked + div {
            font-weight: bold;
            color: #FF4B4B;
        }
    </style>
""", unsafe_allow_html=True)

# Initialize Notion client
NOTION_TOKEN = "ntn_S6159294934albrajfceBHL4szrrrMllKAcFNUGM62v7JI"
DATABASE_ID = "18316f1f61d680a2921bd08b8c62f895"

def fetch_notion_data():
    """Fetch data from Notion database"""
    if not NOTION_TOKEN:
        st.error("Please set your NOTION_TOKEN in the .env file")
        return None
        
    notion = Client(auth=NOTION_TOKEN)
    
    try:
        # Query the database
        response = notion.databases.query(
            database_id=DATABASE_ID
        )
        
        # Process the response into a dataframe
        data = []
        for page in response['results']:
            properties = page.get('properties', {})
            if not properties:
                continue
                
            # Helper function to safely get text content
            def get_text_content(prop_value, prop_type='rich_text'):
                if not prop_value:
                    return ''
                try:
                    if prop_type == 'rich_text':
                        texts = prop_value.get('rich_text', [])
                        if not texts:
                            return ''
                        first_text = texts[0].get('text', {})
                        return first_text.get('content', '')
                    elif prop_type == 'title':
                        titles = prop_value.get('title', [])
                        if not titles:
                            return ''
                        first_title = titles[0].get('text', {})
                        return first_title.get('content', '')
                except (AttributeError, IndexError, KeyError):
                    return ''
                return ''

            # Extract data with safe fallbacks
            try:
                row = {
                    'Contact 1 name': get_text_content(properties.get('Contact 1 name')),
                    'Contact 1 phone': properties.get('Contact 1 phone', {}).get('phone_number', ''),
                    'Address': get_text_content(properties.get('Address')),
                    'Last contact date': properties.get('Last contact date', {}).get('date', {}).get('start', ''),
                    'Status of Claim': properties.get('Status of Claim', {}).get('status', {}).get('name', ''),  
                    'Notes': get_text_content(properties.get('Notes')),
                    'Task': get_text_content(properties.get('Task'))
                }
                # Only add row if it has at least some data
                if any(row.values()):
                    data.append(row)
            except:
                continue
            
        df = pd.DataFrame(data)
        if df.empty:
            st.warning("No data found in the Notion database")
            return None
            
        return df
        
    except Exception as e:
        st.error(f"Error fetching Notion data: {str(e)}")
        return None

def create_funnel_chart(df):
    """Create a funnel chart from lead status data"""
    if 'Status of Claim' not in df.columns:
        return None
        
    # Define the desired order of statuses
    status_order = [
        'Not approved by client',
        'Approved and waiting for filled documents',
        'Filled documents recived',
        'Sent to Attorney',
        'Done'
    ]
    
    # Count the number of leads in each status
    status_counts = df['Status of Claim'].value_counts()
    
    # Create ordered data for the funnel
    ordered_values = []
    ordered_labels = []
    for status in status_order:
        if status in status_counts.index:
            ordered_labels.append(status)
            ordered_values.append(status_counts[status])
        else:
            ordered_labels.append(status)
            ordered_values.append(0)
    
    # Create funnel chart
    fig = go.Figure(go.Funnel(
        y=ordered_labels,
        x=ordered_values,
        textinfo="value+percent initial"
    ))
    
    # Update layout
    fig.update_layout(
        title="Claims Status Funnel",
        width=800,
        height=500,
        showlegend=False
    )
    
    return fig

# Create the sidebar with better styling
st.sidebar.markdown("""
    <div style='text-align: center; padding: 1rem;'>
        <div class='sidebar-title'>
            🏢 TrueClaim
        </div>
        <div class='sidebar-subtitle'>
            Claims Management System
        </div>
    </div>
""", unsafe_allow_html=True)

# Navigation with icons
st.sidebar.markdown("""
    <div style='padding: 0 1rem;'>
        <h3 style='color: #31333F; font-size: 1.1em; margin-bottom: 1rem;'>NAVIGATION</h3>
    </div>
""", unsafe_allow_html=True)

# Define navigation items with their labels
nav_items = {
    "🏠 Dashboard": "Dashboard",
    "📞 New Call": "New Call",
    "📊 Batch Calls": "Batch Calls"
}

selected_tab = st.sidebar.radio(
    "",
    list(nav_items.keys()),
    format_func=lambda x: nav_items[x],
    key="nav_radio"
)

# Add divider
st.sidebar.markdown("<hr style='margin: 2rem 0; opacity: 0.2;'>", unsafe_allow_html=True)

# System status with better styling
st.sidebar.markdown("""
    <div style='padding: 0 1rem;'>
        <h3 style='color: #31333F; font-size: 1.1em; margin-bottom: 1rem;'>SYSTEM STATUS</h3>
    </div>
""", unsafe_allow_html=True)

st.sidebar.markdown("""
    <div style='background-color: white; padding: 1rem; border-radius: 5px; margin: 0.5rem 1rem; box-shadow: 0 1px 2px rgba(0,0,0,0.1);'>
        <div style='color: #666; font-size: 0.9em;'>
            <div style='margin-bottom: 0.8rem; display: flex; justify-content: space-between; align-items: center;'>
                <span>API Status</span>
                <span style='color: #00C853;'>●</span>
            </div>
            <div style='margin-bottom: 0.8rem; display: flex; justify-content: space-between; align-items: center;'>
                <span>Database</span>
                <span style='color: #00C853;'>●</span>
            </div>
            <div style='display: flex; justify-content: space-between; align-items: center;'>
                <span>Last Sync</span>
                <span style='color: #666; font-size: 0.8em;'>Just now</span>
            </div>
        </div>
    </div>
""", unsafe_allow_html=True)

# Add footer with better styling
st.sidebar.markdown("""
    <div style='position: fixed; bottom: 0; left: 0; width: 100%; padding: 1rem; background-color: #f8f9fa; border-top: 1px solid #eee; text-align: center;'>
        <div style='opacity: 0.8; font-size: 0.8em;'>
            <div style='margin-bottom: 0.5rem; color: #666;'>
                Powered by TrueClaim AI
            </div>
            <div style='color: #999; font-size: 0.9em;'>
                Version 1.0.0
            </div>
        </div>
    </div>
""", unsafe_allow_html=True)

# Get the clean label without emoji
current_page = nav_items[selected_tab]

# Create the main UI
if current_page == "Dashboard":  
    st.title("Claims Dashboard")
    
    # Fetch data for analytics
    df = fetch_notion_data()
    
    if df is not None:
        # Quick Statistics in cards
        st.subheader("📊 Overview")
        
        # Funnel Chart in a nice container
        st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
        funnel_fig = create_funnel_chart(df)
        if funnel_fig:
            st.plotly_chart(funnel_fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
                <div class='status-card'>
                    <h3 style='color: #FF4B4B;'>Total Claims</h3>
                    <h2>{}</h2>
                </div>
            """.format(len(df)), unsafe_allow_html=True)
            
        with col2:
            st.markdown("""
                <div class='status-card'>
                    <h3 style='color: #FF4B4B;'>Status Types</h3>
                    <h2>{}</h2>
                </div>
            """.format(df['Status of Claim'].nunique()), unsafe_allow_html=True)
            
        with col3:
            st.markdown("""
                <div class='status-card'>
                    <h3 style='color: #FF4B4B;'>Active Phone Numbers</h3>
                    <h2>{}</h2>
                </div>
            """.format(df['Contact 1 phone'].notna().sum()), unsafe_allow_html=True)
        
        
elif current_page == "New Call":
    st.title("Make a Single Call")
    
    # Create two columns for input fields
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("<div class='input-container'>", unsafe_allow_html=True)
        phone_number = st.text_input("📱 Phone Number", placeholder="+1234567890")
        customer_name = st.text_input("👤 Customer Name")
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col2:
        st.markdown("<div class='input-container'>", unsafe_allow_html=True)
        aigent_Name = st.text_input("📱 Aigent Name", placeholder="John Doe")
        address = st.text_input("🏠 Address")
        st.markdown("</div>", unsafe_allow_html=True)
    
    task = st.text_area("🎯 Task/Script", height=100)
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        if st.button("📞 Make Call"):
            if not phone_number or not task:
                st.error("Please fill in both phone number and task fields")
            else:
                BLEND_API_KEY = "org_ba2e4ccfb75e56afc088d9804df57d2623542e8bbd3de2c02bfcb0024daa778c1850bba9de94a2d1ec6a69"
  # Get API key from environment variable
                # Headers
                headers = {
                    'Authorization': BLEND_API_KEY,
                    'x-bland-org-id': 'da9f344c-390c-4d2b-98a6-be62a74b29f4'
                }

                # Data
                data = {
                    "phone_number": phone_number,
                    "from": None,
                    "task": task,
                    "model": "turbo",
                    "language": "en",
                    "voice": "Public - June 2978",
                    "voice_settings": {},
                    "pathway_id": "6a5a0412-6481-4533-b560-cf72283e956b",
                    "local_dialing": False,
                    "max_duration": 12,
                    "answered_by_enabled": False,
                    "wait_for_greeting": False,
                    "noise_cancellation": False,
                    "record": False,
                    "amd": False,
                    "interruption_threshold": 100,
                    "voicemail_message": None,
                    "temperature": None,
                    "transfer_phone_number": None,
                    "transfer_list": {},
                    "metadata": None,
                    "pronunciation_guide": [],
                    "start_time": None,
                    "background_track": "none",
                    "request_data": {
                        "customer name": customer_name,
                        "home address": address,
                        "aigent name": aigent_Name,
                    },
                    "tools": [],
                    "dynamic_data": [],
                    "analysis_preset": None,
                    "analysis_schema": {},
                    "webhook": None,
                    "calendly": {},
                    "timezone": "America/Los_Angeles"
                }

                try:
                    # Make the API call
                    response = requests.post(
                        "https://api.bland.ai/v1/calls",
                        headers=headers,
                        json=data
                    )
                    
                    # Display the response
                    st.json(response.json())
                    
                except Exception as e:
                    st.error(f"Error making API call: {str(e)}")

else:  # Batch Calls tab
    st.title("Batch Calls from Database")
    
    # Fetch and display data
    df = fetch_notion_data()
    
    if df is not None:
        st.markdown("""
            <div style='background-color: #f0f2f6; padding: 1rem; border-radius: 5px; margin-bottom: 1rem;'>
                <h3 style='color: #FF4B4B;'>📊 Current Database Status</h3>
                <p>Review the data below before making batch calls.</p>
            </div>
        """, unsafe_allow_html=True)
        
        # Display the dataframe with better styling
        styled_df = (
            df.style
            .set_properties(**{'background-color': '#f9f9f9', 'color': '#31333F'})
            .apply(lambda x: ['background-color: #ffeded' if pd.isna(v) else '' for v in x])
        )
        st.dataframe(styled_df)
        
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            if st.button("📞 Start Batch Calls"):
                BLEND_API_KEY = "org_ba2e4ccfb75e56afc088d9804df57d2623542e8bbd3de2c02bfcb0024daa778c1850bba9de94a2d1ec6a69"  # Get API key from environment variable
                df = df.dropna(subset=['Contact 1 phone', 'Task'])
                st.info("Starting batch calls...")
                progress_bar = st.progress(0)
                
                for index, row in df.iterrows():
                    progress = (index + 1) / len(df)
                    progress_bar.progress(progress)
                    
                    data = {
                        "phone_number": row['Contact 1 phone'],
                        "task": row['Task'],
                        "model": "turbo",
                        "language": "en",
                        "voice": "Public - June 2978",
                        "voice_settings": {},
                        "pathway_id": "6a5a0412-6481-4533-b560-cf72283e956b",
                        "local_dialing": False,
                        "max_duration": 12,
                        "answered_by_enabled": False,
                        "wait_for_greeting": False,
                        "noise_cancellation": False,
                        "record": False,
                        "amd": False,
                        "interruption_threshold": 100,
                        "voicemail_message": None,
                        "temperature": None,
                        "transfer_phone_number": None,
                        "transfer_list": {},
                        "metadata": None,
                        "pronunciation_guide": [],
                        "start_time": None,
                        "background_track": "none",
                        "request_data": {
                            "customer name": row['Contact 1 name'],
                            "home address": row['Address'],
                            "status": row['Status of Claim'],
                            "last contact": row['Last contact date'],
                            "notes": row['Notes']
                        },
                        "tools": [],
                        "dynamic_data": [],
                        "analysis_preset": None,
                        "analysis_schema": {},
                        "webhook": None,
                        "calendly": {},
                        "timezone": "America/Los_Angeles"
                    }
                    
                    try:
                        headers = {
                            'Authorization': BLEND_API_KEY,
                            'x-bland-org-id': 'da9f344c-390c-4d2b-98a6-be62a74b29f4'
                        }
                        response = requests.post(
                            "https://api.bland.ai/v1/calls",
                            headers=headers,
                            json=data
                        )
                        st.write(f"Call for {row['Contact 1 name']}: {response.json()}")
                    except Exception as e:
                        st.error(f"Error in call for {row['Contact 1 name']}: {str(e)}")
                    
                st.success("Batch calls completed!")
