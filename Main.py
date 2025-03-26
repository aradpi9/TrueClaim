import streamlit as st
import requests
import json
import os
import pandas as pd
from notion_client import Client
import plotly.graph_objects as go
from datetime import datetime
import subprocess
import sys



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

# Constants for database IDs
DATABASE_ID = "18316f1f61d680a2921bd08b8c62f895"
MARKETING_DATABASE_ID = "1c216f1f61d680c28534e5466d8f98d4"
NOTION_TOKEN = "ntn_S6159294934albrajfceBHL4szrrrMllKAcFNUGM62v7JI"

# Initialize Notion client
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
                

            # Extract data with safe fallbacks
            try:
                row = {
                    'notion raw id': page['id'],
                    'customer name': page['properties']['First name']['title'][0]['plain_text'],
                    'customer last name': page['properties']['Last name']['rich_text'][0]['plain_text'],
                    'Phone': page['properties']['Main contact phone']['phone_number'],
                    'Email': page['properties']['Main contact Email']['email'],
                    'Email collected': page['properties']['Main contact Email collected']['email'],
                    'home address': page['properties']['Property Street']['rich_text'][0]['plain_text'],
                    'Next Follow Up Date': page['properties']['Next Follow Up Date']['date']['start'] if page['properties']['Next Follow Up Date']['date'] else '',
                    'Claim': page['properties']['Status of Claim']['status']['name'],
                    'Lead': page['properties']['Status of lead']['status']['name'],   
                    'call id' : page['properties']['Last call ID']['rich_text'][0]['plain_text'] if page['properties']['Last call ID']['rich_text'] else '',
                    'cold call summary': page['properties']['cold call summary']['rich_text'][0]['plain_text'] if page['properties']['cold call summary']['rich_text'] else '',
                    'Active': page['properties']['Active']['select']['name']
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
        
        df['Next Follow Up Date'] = pd.to_datetime(df['Next Follow Up Date'], utc=True).dt.tz_convert('America/New_York') + pd.Timedelta(hours = 5)

            
        return df
        
    except Exception as e:
        st.error(f"Error fetching Notion data: {str(e)}")
        return None

def create_funnel_chart(df):
    """Create a funnel chart from lead status data"""
    if 'Claim' not in df.columns:
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
    status_counts = df['Claim'].value_counts()
    
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
    "📊 Batch Calls": "Batch Calls",
    "📥 Update Database": "Update Database",
    "Server run" : "Server run"
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
                <span>Server Status</span>
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
        
        # Create two columns for charts
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            # Funnel Chart in a nice container
            st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
            funnel_fig = create_funnel_chart(df)
            if funnel_fig:
                st.plotly_chart(funnel_fig, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
        
        with chart_col2:
            # Add Pie Chart for Active Status
            st.subheader("📈 Active Status Distribution")
            st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
            
            # Calculate active vs inactive counts
            status_counts = df['Active'].value_counts()
            active_count = len(df[df['Active'] == 'Yes'])
            inactive_count = len(df[df['Active'] != 'Yes'])
            
            # Create pie chart
            pie_data = [
                dict(
                    type='pie',
                    labels=['Active', 'Inactive'],
                    values=[active_count, inactive_count],
                    hole=0.4,
                    marker=dict(colors=['#2ecc71', '#e74c3c'])
                )
            ]
            
            pie_layout = dict(
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                height=400,
                margin=dict(t=0, b=0, l=0, r=0)
            )
            
            pie_fig = dict(data=pie_data, layout=pie_layout)
            st.plotly_chart(pie_fig, use_container_width=True)
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
            """.format(df['Claim'].nunique()), unsafe_allow_html=True)
            
        with col3:
            st.markdown("""
                <div class='status-card'>
                    <h3 style='color: #FF4B4B;'>Active Phone Numbers</h3>
                    <h2>{}</h2>
                </div>
            """.format(df['Phone'].notna().sum()), unsafe_allow_html=True)
        
        
elif current_page == "New Call":
    st.title("Make a Single Call")
    
    # Create two columns for input fields
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("<div class='input-container'>", unsafe_allow_html=True)
        Customer_phone_number = st.text_input("📱 Phone Number", placeholder="+1234567890")
        Customer_name = st.text_input("👤 Customer Name")
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col2:
        st.markdown("<div class='input-container'>", unsafe_allow_html=True)
        Agent_name = st.text_input("📱 Agent Name", placeholder="Christin")
        Home_address = st.text_input("🏠 Address")
        st.markdown("</div>", unsafe_allow_html=True)
    
    Agent_task = st.selectbox("🎯 Task", ["Cold caller", "Closer representative"])
    
    # Show additional fields for Closer representative
    specialist_name = None
    first_call_summary = None
    if Agent_task == "Closer representative":
        specialist_name = st.text_input("👨‍⚕️ Specialist Name")
        first_call_summary = st.text_area("📝 First Call Summary", height=100)
    
    Agent_voice = "Public - June 2978" if "Cold caller" in Agent_task else "mason (da9f34)" if "Closer representative" in Agent_task else None
    Agent_task = "6a5a0412-6481-4533-b560-cf72283e956b" if "Cold caller" in Agent_task else "29e7ef67-4d36-4d15-aa09-0a38642fea26" if "Closer representative" in Agent_task else None

    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        if st.button("📞 Make Call"):
            if not Customer_phone_number or not Agent_task:
                st.error("Please fill in both phone number and task fields")
            elif Agent_task == "29e7ef67-4d36-4d15-aa09-0a38642fea26" and (not specialist_name or not first_call_summary):
                st.error("Please fill in specialist name and first call summary")
            else:
                BLEND_API_KEY = "org_ba2e4ccfb75e56afc088d9804df57d2623542e8bbd3de2c02bfcb0024daa778c1850bba9de94a2d1ec6a69"  # Get API key from environment variable
                # Get API key from environment variable
                # Headers
                headers = {
                   'Authorization': BLEND_API_KEY,
                   'Content-Type': 'application/json'
                }

                # Data
                data = {
                    "phone_number": Customer_phone_number,
                    "task": "",
                    "from": "+13363603640",
                    "model": "enhanced",
                    "language": "en",
                    "voice": Agent_voice,
                    "voice_settings": {},
                    "pathway_id": Agent_task,
                    "local_dialing": False,
                    "max_duration": "12",
                    "answered_by_enabled": False,
                    "wait_for_greeting": True,
                    "noise_cancellation": True,
                    "ignore_button_press": True,
                    "record": False,
                    "amd": False,
                    "interruption_threshold": 100,
                    "voicemail_message": "test",
                    "temperature": 1,
                    "transfer_list": {},
                    "pronunciation_guide": [],
                    "request_data": {
                    "customer name": Customer_name,
                    "home address": Home_address,
                    "agent name": Agent_name,
                    "specialist name": specialist_name,
                    "first call summary": first_call_summary
                    },
                    "dynamic_data": [],
                    "analysis_schema": {},
                    "calendly": {},
                    "timezone": "America/New_York"

                }
                
                # Add specialist info to request_data if it's a closer call
                if Agent_task == "29e7ef67-4d36-4d15-aa09-0a38642fea26":
                    data["request_data"].update({
                        "specialist_name": specialist_name,
                        "first_call_summary": first_call_summary
                    })
                
                try:
                    # Make the API call
                    response = requests.request("POST"
                                                , "https://api.bland.ai/v1/calls"
                                                , json=data
                                                , headers=headers)
                    
                    # Display the response
                    st.json(response.json())
                    
                except Exception as e:
                    st.error(f"Error making API call: {str(e)}")

elif current_page == "Update Database":
    st.title("Update Database")
    
    # Initialize session state for storing page IDs if not exists
    if 'last_uploaded_pages' not in st.session_state:
        st.session_state.last_uploaded_pages = []
    if 'last_uploaded_second_pages' not in st.session_state:
        st.session_state.last_uploaded_second_pages = []
    
    def update_notion_database(df):
        notion = Client(auth=NOTION_TOKEN)
        success_count = 0
        error_count = 0
        
        # Function to create rich text content
        def create_rich_text(content):
            if pd.isna(content) or content == '' or content is None:
                return {"rich_text": []}
            # Filter out "nan" strings
            content_str = str(content).strip()
            if content_str.lower() == 'nan':
                return {"rich_text": []}
            return {"rich_text": [{"text": {"content": content_str}}]}
        
        # Function to create title content
        def create_title(content):
            if pd.isna(content) or content == '' or content is None:
                return {"title": []}
            # Filter out "nan" strings
            content_str = str(content).strip()
            if content_str.lower() == 'nan':
                return {"title": []}
            return {"title": [{"text": {"content": content_str}}]}
        
        # Function to create date content
        def create_date(date_str):
            if pd.isna(date_str) or date_str == '' or date_str is None:
                return {"date": None}
            try:
                # Try to parse the date string into a datetime object
                date_obj = pd.to_datetime(date_str)
                # Format the date as ISO 8601 string
                return {"date": {"start": date_obj.strftime("%Y-%m-%d")}}
            except (ValueError, TypeError):
                return {"date": None}
        
        # Function to create number content
        def create_number(value):
            if pd.isna(value) or value == '' or value is None:
                return {"number": None}
            try:
                # Remove any non-numeric characters and convert to float
                cleaned_value = ''.join(filter(str.isdigit, str(value)))
                return {"number": float(cleaned_value)} if cleaned_value else {"number": None}
            except (ValueError, TypeError):
                return {"number": None}
        
        # Function to create phone number content
        def create_phone(number):
            if pd.isna(number) or number == '' or number is None:
                return {"phone_number": None}
            # Filter out "nan" strings
            number_str = str(number).strip()
            if number_str.lower() == 'nan':
                return {"phone_number": None}
            return {"phone_number": number_str}
        
        # Function to create email content
        def create_email(email):
            if pd.isna(email) or email == '' or email is None:
                return {"email": None}
            # Filter out "nan" strings
            email_str = str(email).strip()
            if email_str.lower() == 'nan':
                return {"email": None}
            return {"email": email_str}
        
        # Function to combine multiple values with comma
        def combine_values(row, columns):
            values = []
            for col in columns:
                if col in row:
                    value = str(row[col]).strip()
                    if value.lower() != 'nan':  # Skip "nan" values
                        # Remove .0 suffix if present for phone numbers
                        if value.endswith('.0'):
                            value = value[:-2]
                        values.append(value)
            return ', '.join(values) if values else None
        
        progress_bar = st.progress(0, text="Processing rows...")
        status_text = st.empty()
        
        for index, row in df.iterrows():
            try:
                # Prepare phone numbers and emails
                phones = combine_values(row, ['Phone 1', 'Phone 2', 'Phone 3', 'Phone 4', 'Phone 5'])
                emails = combine_values(row, ['Email 1', 'Email 2', 'Email 3', 'Email 4', 'Email 5'])
                print(phones, emails)
                # Process relatives data
                relative_names = combine_values(row, ['RELATIVE 1: Name', 'RELATIVE 2: Name', 'RELATIVE 3: Name'])
                relative_phones = combine_values(row, ['RELATIVE 1: Phone', 'RELATIVE 2: Phone', 'RELATIVE 3: Phone'])
                relative_emails = combine_values(row, ['RELATIVE 1: Email', 'RELATIVE 2: Email', 'RELATIVE 3: Email'])

                # Create the page with proper property formatting
                new_page = {
                    "parent": {"database_id": DATABASE_ID},
                    "properties": {
                        "Surplus Amount": create_number(row.get('Surplus Amount')),
                        "Closing Bid": create_number(row.get('Closing Bid')),
                        "Opening Bid": create_number(row.get('Opening Bid')),
                        "Date sold": create_date(row.get('Date Sold')),
                        "Case number": create_rich_text(row.get('Case Number')),
                        "Parcel Number": create_rich_text(row.get('Parcel Number')),
                        "Type of foreclosure": create_rich_text(row.get('Type of foreclosure')),
                        "First name": create_title(row.get('First Name')),
                        "Last name": create_rich_text(row.get('Last Name')),
                        "Main contact phone": create_phone(phones),
                        "Main contact Email": create_email(emails),
                        "Property Street": create_rich_text(row.get('Property Street')),
                        "Property City": create_rich_text(row.get('Property City')),
                        "Property State": create_rich_text(row.get('Property State')),
                        "Property ZIP Code": create_number(row.get('Property ZIP Code')),
                        "Mailing address": create_rich_text(row.get('Mailing Address')),
                        "Mailing City": create_rich_text(row.get('Mailing City')),
                        "Mailing State": create_rich_text(row.get('Mailing State')),
                        "Mailing Zip Code": create_number(row.get('Mailing Zip Code')),
                        "County": create_rich_text(row.get('County')),
                        "Relative name": create_rich_text(relative_names),
                        "Relative phone": create_phone(relative_phones),
                        "Relative Email": create_email(relative_emails),
                        "Active": {"select": {"name": "No"}}
                    }
                }
                
                # Create the second page for the second database with the requested mapping
                current_time = datetime.now().isoformat()
                second_page = {
                    "parent": {"database_id": MARKETING_DATABASE_ID},
                    "properties": {
                        "Date sold": create_date(row.get('Date Sold')),
                        "First name": create_title(row.get('First Name')),
                        "Last name": create_rich_text(row.get('Last Name')),
                        "Main contact phone": create_phone(phones),
                        "Main contact Email": create_email(emails),
                        "Property Street": create_rich_text(row.get('Property Street')),
                        "Property City": create_rich_text(row.get('Property City')),
                        "Property State": create_rich_text(row.get('Property State')),
                        "Property ZIP Code": create_number(row.get('Property ZIP Code')),
                        "County": create_rich_text(row.get('County')),
                        "Active": {"select": {"name": "No"}},
                        "Campaign start date": {"date": {"start": current_time}},
                        "Campaign state": {"select": {"name": "1"}},
                        "Answered?": {"select": {"name": "No"}}
                    }
                }
                
                # Remove any properties with empty values for first database
                properties_to_remove = []
                for prop_name, prop_value in new_page["properties"].items():
                    if (prop_value.get("rich_text", []) == [] and "rich_text" in prop_value) or \
                       (prop_value.get("number") is None and "number" in prop_value) or \
                       (prop_value.get("phone_number") is None and "phone_number" in prop_value) or \
                       (prop_value.get("email") is None and "email" in prop_value) or \
                       (prop_value.get("date") is None and "date" in prop_value) or \
                       (prop_value.get("title", []) == [] and "title" in prop_value):
                        properties_to_remove.append(prop_name)
                
                for prop_name in properties_to_remove:
                    del new_page["properties"][prop_name]
                
                # Remove any properties with empty values for second database
                properties_to_remove = []
                for prop_name, prop_value in second_page["properties"].items():
                    if (prop_value.get("rich_text", []) == [] and "rich_text" in prop_value) or \
                       (prop_value.get("number") is None and "number" in prop_value) or \
                       (prop_value.get("phone_number") is None and "phone_number" in prop_value) or \
                       (prop_value.get("email") is None and "email" in prop_value) or \
                       (prop_value.get("date") is None and "date" in prop_value) or \
                       (prop_value.get("title", []) == [] and "title" in prop_value):
                        properties_to_remove.append(prop_name)
                
                for prop_name in properties_to_remove:
                    del second_page["properties"][prop_name]
                
                try:
                    # Create the page in both Notion databases
                    first_response = notion.pages.create(**new_page)
                    second_response = notion.pages.create(**second_page)
                    
                    success_count += 1
                    st.session_state.last_uploaded_pages.append(first_response['id'])  # Store the first page ID
                    st.session_state.last_uploaded_second_pages.append(second_response['id'])  # Store the second page ID
                except Exception as e:
                    error_count += 1
                    st.error(f"Error creating page: {str(e)}")
                finally:
                    # Update progress
                    progress = (index + 1) / len(df)
                    progress_bar.progress(progress, text=f"Processing row {index + 1} of {len(df)}")
                    status_text.text(f"Status: {success_count} successful, {error_count} errors")
            
            except Exception as e:
                st.error(f"Error processing row {index + 1}: {str(e)}")
        
        st.success(f"Successfully added {success_count} records to Notion database. {error_count} records failed.")
        
        return success_count, error_count
        
    # File upload section with explicit label
    uploaded_file = st.file_uploader("Upload File", type=['csv', 'xlsx', 'xls'], label_visibility="visible")
    
    if uploaded_file is not None:
        try:
            # Read the file based on its type and convert data types
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:  # Excel file
                df = pd.read_excel(uploaded_file)
            
            # Convert numeric columns to string to avoid Arrow serialization issues
            numeric_columns = df.select_dtypes(include=['float64', 'int64']).columns
            for col in numeric_columns:
                df[col] = df[col].astype(str)
            
            # Show basic information about the data
            st.subheader("File Preview")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="Total Rows", value=str(len(df)))
            with col2:
                st.metric(label="Total Columns", value=str(len(df.columns)))
            with col3:
                st.metric(label="File Size", value=f"{uploaded_file.size/1024:.2f} KB")
            
            # Display column information with explicit labels
            st.subheader("Column Information")
            col_info = pd.DataFrame({
                'Column Name': df.columns,
                'Non-Null Count': df.count().values,
                'Null Count': df.isnull().sum().values
            })
            st.dataframe(col_info, hide_index=True, use_container_width=True)
            
            # Show data preview with explicit label
            st.subheader("Data Preview (First 5 Rows)")
            st.dataframe(df.head(5), hide_index=True, use_container_width=True)
            
            # Add a button to confirm upload with explicit label and help text
            if st.button(
                label="✅ Confirm and Update Database",
                help="Click to start updating the Notion database",
                type="primary"
            ):
                with st.spinner("Updating Notion database..."):
                    success_count, error_count = update_notion_database(df)
            
            # Add Set as Active button outside the update function
            if st.session_state.last_uploaded_pages:
                if st.button("🔄 Set as Active", type="primary", help="Click to set all newly added records as Active", key="set_active"):
                    notion = Client(auth=NOTION_TOKEN)
                    with st.spinner("Setting records as Active..."):
                        active_success = 0
                        active_error = 0
                        
                        # Create a progress bar for activation
                        active_progress = st.progress(0)
                        total_pages = len(st.session_state.last_uploaded_pages)
                        
                        for i, (page_id, second_page_id) in enumerate(zip(st.session_state.last_uploaded_pages, st.session_state.last_uploaded_second_pages)):
                            try:
                                # Update the page's Active property to "Yes" in first database
                                notion.pages.update(
                                    page_id=page_id,
                                    properties={
                                        "Active": {"select": {"name": "Yes"}}
                                    }
                                )
                                
                                # Update the page's Active property to "Yes" in second database
                                notion.pages.update(
                                    page_id=second_page_id,
                                    properties={
                                        "Active": {"select": {"name": "Yes"}}
                                    }
                                )
                                
                                active_success += 1
                            except Exception as e:
                                active_error += 1
                                st.error(f"Error updating page {page_id} or {second_page_id}: {str(e)}")
                            
                            active_progress.progress((i + 1) / total_pages)
                        
                        if active_success > 0:
                            st.success(f"Successfully set {active_success} records as Active in both databases. {active_error} updates failed.")
                            st.session_state.last_uploaded_pages = []  # Clear the lists after activation
                            st.session_state.last_uploaded_second_pages = []
        
        except Exception as e:
            st.error(f"Error reading file: {str(e)}")
            st.info("Please make sure your file is properly formatted and try again.")

elif current_page == "Batch Calls":  # Batch Calls tab
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
                            "status": row['Claim'],
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

elif current_page == "Server run":
    st.title("Server Run")
    
    # Fetch and display data
    df = fetch_notion_data()
    cold_call_df = df[((df['Lead'] == 'New') 
        & (df['Active'] == 'Yes')) 
        | ((df['Lead'] == 'Did not answered') 
        & (df['Next Follow Up Date'] < pd.Timestamp.now(tz='America/New_York')) 
        & (df['Active'] == 'Yes'))]   
    
    closer_call_df = df[(df['Lead'] == 'Interested') 
        & (df['Active'] == 'Yes') 
        & (df['Next Follow Up Date'] < pd.Timestamp.now(tz='America/New_York'))]
    
    if cold_call_df is not None:
        st.markdown("""
            <div style='background-color: #f0f2f6; padding: 0.5rem; border-radius: 5px; margin-bottom: 0.5rem; text-align: center;'>
                <h3 style='color: #4CAF50;'>Cold call ready list </h3>
                <p>Table below represent the current leads which are applicalble for cold call</p>
            </div>
        """, unsafe_allow_html=True)
        
        # Display the dataframe with better styling
        cold_call_df_styled_df = (
            cold_call_df.style
            .set_properties(**{'background-color': '#f9f9f9', 'color': '#31333F'})
            .apply(lambda x: ['background-color: #ffeded' if pd.isna(v) else '' for v in x])
        )
        
        st.dataframe(cold_call_df_styled_df)

                # Add a button to start batch calls
        if st.button("Start cold call server"):           
            result = subprocess.run([sys.executable, "Cold_call_Server_run.py"], capture_output=True, text=True)
            st.write(result.stdout)
            


            
    if closer_call_df is not None:
        st.markdown("""
            <div style='background-color: #f0f2f6; padding: 0.5rem; border-radius: 5px; margin-bottom: 0.5rem; text-align: center;'>
                <h3 style='color: #4CAF50;'>Closer call ready list </h3>
                <p>Table below represent the current leads which are applicalble for closer call</p>
            </div>
        """, unsafe_allow_html=True)
        
        # Display the dataframe with better styling
        closer_call_df_styled_df = (
            closer_call_df.style
            .set_properties(**{'background-color': '#f9f9f9', 'color': '#31333F'})
            .apply(lambda x: ['background-color: #ffeded' if pd.isna(v) else '' for v in x])
        )
        
        st.dataframe(closer_call_df_styled_df)

        # Add a button to start batch calls
        if st.button("Start closer call server"):           
            pass
