# %% [markdown]
# thing to add:
# 
# - [ ] add Logging for all
# - [ ] add "did not answer" counter, and set cold caller df pulling logic accordingly.
# - [ ] add SMS communication in addtion to Mail.
# - [ ] add "call hang out for some reason" logic.
# 

# %% [markdown]
# improts

# %%
# imports
import requests
import pandas as pd
from notion_client import Client
import datetime
import json
import time
import logging
import os

# %% [markdown]
# Configure logging

# %%
log_directory = "logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

log_filename = f"batch_calls_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
log_filepath = os.path.join(log_directory, log_filename)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filepath),
        logging.StreamHandler()  # This will also print to notebook output
    ]
)
logger = logging.getLogger(__name__)

# %% [markdown]
# Setup

# %%
# BLENDAPI setup
BLEND_API_KEY = "org_ba2e4ccfb75e56afc088d9804df57d2623542e8bbd3de2c02bfcb0024daa778c1850bba9de94a2d1ec6a69"
Blend_url = "https://api.bland.ai/v1/calls"
Blend_SMS_url = "https://api.bland.ai/v1/sms/messages"

# groq setup
GROQ_API_KEY = "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"
groq_url = "https://api.groq.com/openai/v1/chat/completions"

# Initialize Notion client
NOTION_TOKEN = "ntn_S6159294934albrajfceBHL4szrrrMllKAcFNUGM62v7JI"
DATABASE_ID = "18316f1f61d680a2921bd08b8c62f895"
notion = Client(auth=NOTION_TOKEN)

# call script setup
COLD_CALL_SCRIPT = "6a5a0412-6481-4533-b560-cf72283e956b"
CLOSER_CALL_SCRIPT = "29e7ef67-4d36-4d15-aa09-0a38642fea26"


# call general information
System_phone_number = "+14702354347"
Interruption_Threshold_in_ms = 50
LLM_temperature = 0.9
Agent_name = "Christin"
Cold_Agent_voice = "June"
Specialist_name = "David"
Closer_Agent_voice = "mason (da9f34)"

# ZOHO setup
ZOHO_CLIENT_ID = "1000.VO682Z1FM15RTS0EPC3QG9OR3ZA81J" # info@trueclaim.org client ID
ZOHO_CLIENT_SECRET = "73966cb9ddadac75baa08767dc1e8fd4caaa758b54" # info@trueclaim.org client secret
ZOHO_REFRESH_TOKEN = "1000.8e189778917bde78b6b8fd1fced5a6f8.b34bcab0a7248cf421fc8608c134348e"  # This is the long-lived token you received initially
ZOHO_ACCOUNT_ID = "3454657000000008002" # info@trueclaim.org Account ID
Zoho_auth_token = "1"
ZOHO_URL = f"https://mail.zoho.com/api/accounts/{ZOHO_ACCOUNT_ID}/messages"


# %% [markdown]
# function definition

# %%
def pull_notion_data(type="all"):
    """
    Retrieves and filters data from a Notion database based on the specified type.
    
    Args:
        type (str): The type of data to pull - "cold" for new/unanswered leads, 
                   "closer" for follow-up calls, or any other value for all data.
    
    Returns:
        pandas.DataFrame: A filtered dataframe containing the requested data.
    """
    
    # Initialize empty array to store the data
    data = []

    # Query the Notion database using the API
    response = notion.databases.query(database_id=DATABASE_ID)

    # Iterate through each page in the database and extract relevant information
    for page in response['results']:
        properties = page.get('properties', {})
        # Extract specific fields from the page properties
        row = {
            'notion raw id': page['id'],
            'customer name': page['properties']['First name']['title'][0]['plain_text'].split(" ")[0],
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
        data.append(row)
    # Convert the collected data into a pandas DataFrame 
    df = pd.DataFrame(data)
    
    # Convert date strings to datetime objects
    df['Next Follow Up Date'] = pd.to_datetime(df['Next Follow Up Date'], utc=True).dt.tz_convert('America/New_York') + pd.Timedelta(hours = 5)

    # Get current UTC time for comparison
    current_time = pd.Timestamp.now(tz='America/New_York')
    
    if type == "cold":

        # Filter for new leads or leads that didn't answer and are past their follow-up date
        return df[((df['Lead'] == 'New') 
                  & (df['Active'] == 'Yes')) 
                  | ((df['Lead'] == 'Did not answered') 
                  & (df['Next Follow Up Date'] < current_time) 
                  & (df['Active'] == 'Yes'))]   
        
    elif type == "closer":
        
        return df[(df['Lead'] == 'Interested') 
                  & (df['Active'] == 'Yes') 
                  & (df['Next Follow Up Date'] < current_time)]

    else:    
        return df
        
def get_follow_up_date_groq(transcription, call_date):
    """
    Uses the Groq API to analyze a call transcript and suggest a follow-up date.
    
    Args:
        transcription (str): The transcript of the call to analyze
        call_date (str): The date when the call was made
    
    Returns:
        str: A suggested follow-up date in ISO 8601 format (YYYY-MM-DD HH:MM:SS)
    """
    # Set up the API headers with authentication
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Prepare the API request payload
    payload = {
        "model": "deepseek-r1-distill-llama-70b",
        "messages": [
            {
                "role": "system", "content": """
                You are an AI assistant tasked with reviewing call transcripts and find specific follow-up date.
                response with the exeact time and date requested by the user, the senior representative is avialable all of the time.
                also the time given to you is GMT time, please convert it to GMT-5 (North Carolina Time zone).
                please resonse with ISO 8601 time and date format, for example: \"2025-02-06 12:00:00\", do not add any other text.
                """
            },
            {
                "role": "user", "content": f"Based on this call transcript, suggest a specific follow-up date: {transcription}, the time of the call is{call_date}"
            }
        ]
    }
    
    # Make the API call and extract the suggested date
    groq_response = requests.post(groq_url, json=payload, headers=headers)
    print (groq_response.json())
    return groq_response.json()['choices'][0]['message']['content'].strip().split('\n')[-1]

def update_data_base_after_closer(notion_raw_id, call_id):
    """
    Updates the Notion database with information from a completed closer call.
    
    Args:
        notion_raw_id (str): The Notion page ID to update
        call_id (str): The ID of the completed call
    """
    # Retrieve call details from the API
    call_id_response = json.loads(requests.request("GET", Blend_url+"/"+call_id, headers=headers).text)

    # Initialize dictionary to store call information
    call_info_dict = {}
    
    # Store basic call information
    call_info_dict["Last call date"] = call_id_response["created_at"]
    call_info_dict["Last call ID"] = call_id
    
    # Handle case where customer want to continue
    if "Documents sent for signiture" in call_id_response["pathway_tags"]:
        
        call_info_dict["Status of lead"] = call_id_response["pathway_tags"][0]
        call_info_dict["closer call summary"] = call_id_response["summary"].split("Here is a concise and insightful summary of the call:\n\n")[1]
        call_info_dict["Status of Claim"] = "Approved and waiting for filled documents"
        # Update Notion database with all collected information
        notion.pages.update(
            page_id=notion_raw_id,
            properties={
                'closer call summary': {
                    'rich_text': [{'text': {'content': call_info_dict["closer call summary"]}}]
                },
                'Status of lead': {
                    'status': {'name': call_info_dict["Status of lead"]}
                },
                'Status of Claim': {
                    'status': {'name': call_info_dict["Status of Claim"]}
                },
                'Last call ID': {
                    'rich_text': [{'text': {'content':call_info_dict["Last call ID"]}}]
                }
            }
        )
        
    # Handle case where customer did not answer
    elif not call_id_response["pathway_tags"]:
        # Set follow-up date to 4 huors after the call

        # update Next Follow Up Date to 4 huors after the call
        call_info_dict["Next Follow Up Date"] = (pd.to_datetime(call_id_response["created_at"]) + pd.Timedelta(hours = 4)).strftime('%Y-%m-%d %H:%M:%S')

        # update notion table with new follow up time and lead status
        notion.pages.update(
            page_id=notion_raw_id,
            properties={
                'Next Follow Up Date': {
                    'date': {
                        'start': call_info_dict["Next Follow Up Date"]
                    }
                }
            }
        )
        
    elif "Not interested" in call_id_response["pathway_tags"]:
        #collect trascription and update notion database
        
        # collect cold call transcription
        call_info_dict["closer call summary"] = call_id_response["summary"].split("Here is a concise and insightful summary of the call:\n\n")[1]
          
        call_info_dict["Status of lead"] = 'Not interested'
        
        # update notion table with new follow up time and lead status
        notion.pages.update(
            page_id=notion_raw_id,
            properties={
                'closer call summary': {
                    'rich_text': [
                        {
                            'text': {
                                'content': call_info_dict["closer call summary"]
                            }
                        }
                    ]
                },
                'Status of lead': {
                    'status': {
                        'name': call_info_dict["Status of lead"]
                    }
                }
            }
        )
        
    else:
        # call got hang out for some reason, need to think what to do
        pass
    
def update_data_base_after_cold_call(notion_raw_id, call_id):
    """
    Updates the Notion database with information from a completed cold call.
    
    Args:
        notion_raw_id (str): The Notion page ID to update
        call_id (str): The ID of the completed call
    """
    # Retrieve call details from the API
    call_id_response = json.loads(requests.request("GET", Blend_url+"/"+call_id, headers=headers).text)

    # Initialize dictionary to store call information
    call_info_dict = {}
    
    # Store basic call information
    call_info_dict["Last call date"] = call_id_response["created_at"]
    call_info_dict["Last call ID"] = call_id
    
    # Handle case where customer showed interest
    if "Interested" in call_id_response["pathway_tags"]:
        # Collect additional information for interested customers
        
        call_info_dict["Main contact Email collected"] = call_id_response["variables"]["email"]
        call_info_dict["Next Follow Up Date"]  = get_follow_up_date_groq(
            call_id_response['concatenated_transcript'],
            call_id_response["created_at"]
        )
        call_info_dict["Status of lead"] = call_id_response["pathway_tags"][0]
        call_info_dict["cold call summary"] = call_id_response["summary"]
        # Update Notion database with all collected information
        notion.pages.update(
            page_id=notion_raw_id,
            properties={
                'cold call summary': {
                    'rich_text': [{'text': {'content': call_info_dict["cold call summary"]}}]
                },
                'Status of lead': {
                    'status': {'name': call_info_dict["Status of lead"]}
                },
                'Main contact Email collected': {
                    'email': call_info_dict["Main contact Email collected"]
                },
                'Next Follow Up Date': {
                    'date': {'start': call_info_dict["Next Follow Up Date"]}
                },
                'Last call ID': {
                    'rich_text': [{'text': {'content':call_info_dict["Last call ID"]}}]
                }
            }
        )
        
    # Handle case where customer did not answer
    elif "Answered" not in call_id_response["pathway_tags"]:
        # Set follow-up date to 2 days after the call

        # update Next Follow Up Date to 7 days after the call
        call_info_dict["Next Follow Up Date"] = (pd.Timestamp.now(tz='America/New_York') + pd.Timedelta(hours = 4)).strftime('%Y-%m-%d %H:%M:%S')
        
        call_info_dict["Status of lead"] = 'Did not answered'
        
        # update notion table with new follow up time and lead status
        notion.pages.update(
            page_id=notion_raw_id,
            properties={
                'Status of lead': {
                    'status': {
                        'name': call_info_dict["Status of lead"]
                    }
                },
                'Next Follow Up Date': {
                    'date': {
                        'start': call_info_dict["Next Follow Up Date"]
                    }
                }
            }
        )
        
    elif "Not interested" in call_id_response["pathway_tags"] and "Answered" in call_id_response["pathway_tags"]:
        #collect trascription and update notion database
        
        # collect cold call summary
        call_info_dict["cold call summary"] = call_id_response["summary"]
          
        call_info_dict["Status of lead"] = 'Not interested'
        
        # update notion table with new follow up time and lead status
        notion.pages.update(
            page_id=notion_raw_id,
            properties={
                'cold call summary': {
                    'rich_text': [
                        {
                            'text': {
                                'content': call_info_dict["cold call summary"]
                            }
                        }
                    ]
                },
                'Status of lead': {
                    'status': {
                        'name': call_info_dict["Status of lead"]
                    }
                }
            }
        )
        
    elif "Asked for follow up" in call_id_response["pathway_tags"]:
        #collect follow up date and update notion DB
        
        # collect cold call transcription   
        call_info_dict["Next Follow Up Date"]  = get_follow_up_date_groq(call_id_response['concatenated_transcript'], call_id_response["created_at"])
        
        call_info_dict["Status of lead"] = 'Asked for follow up'
        
        # update notion table with new follow up time and lead status        
        notion.pages.update(
            page_id=notion_raw_id,
            properties={
                'Status of lead': {
                    'status': {
                        'name': call_info_dict["Status of lead"]
                    }
                },
                'Next Follow Up Date': {
                    'date': {
                        'start': call_info_dict["Next Follow Up Date"]
                    }
                }
            }
        )
        
    else:
        # call got hang out for some reason, need to think what to do
        pass
            
def send_mail(Subject , Content, user_info_df):
    global Zoho_auth_token
    # Headers
    headers = {
        "Authorization": f"Bearer {Zoho_auth_token}",
        "Content-Type": "application/json"
    }
    # collect emails and consider when there are some empty cells:
    email_collected = user_info_df['Email collected'].values[0] or ""
    email_primary = user_info_df['Email'].values[0] or ""
    recipients = list(set(
        [e.strip() for e in email_collected.split(",") if e] +
        [e.strip() for e in email_primary.split(",") if e]
    ))
    Recipients = ','.join(recipients) if recipients else None

    payload = {
        "fromAddress": "info@trueclaim.org",  # Your Zoho email
        "toAddress": Recipients,
        "subject": Subject,
        "content": Content,
        "mailFormat": "html"
    }


    # try to send the mail
    response = requests.post(ZOHO_URL, headers=headers, json=payload)
    response = response.json()

    if response['status']['code'] == 200:
        print("Email sent successfully")

    # check if response failed, if so refresh token
    elif Zoho_auth_token == '1' or response['data']['errorCode'] == 'INVALID_OAUTHTOKEN':

        print("Invalide key, sendinng to refresh")

        # get new auth token
        Zoho_auth_token = refresh_access_token(ZOHO_REFRESH_TOKEN, ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET)

        # update header with new auth token
        headers = {
            "Authorization": f"Bearer {Zoho_auth_token}",
            "Content-Type": "application/json"
        }   
        
        #try to send again
        response = requests.post(ZOHO_URL, headers=headers, json=payload)
        
        # Check if request was successful
        if response.status_code == 200:
            print("Email sent successfully after token refreshed")
        else:
            print(f"Failed to send email. Status code: {response.status_code}")
            print(f"Response: {response.text}")
    
    else: 
        print(f"Failed to send email. Status code: {response.status_code}")
        print(f"Response: {response.text}")
            
def send_SMS(Content, user_info_df):
    phone_numbers = user_info_df['Phone'].values[0].split(', ')
    for phone_number in phone_numbers:
        payload = {
            "to": f"+1{phone_number}",
            "from": System_phone_number,
            "body": Content,
            "sender":Agent_name
            
        }
        headers = {
            "authorization": "org_ba2e4ccfb75e56afc088d9804df57d2623542e8bbd3de2c02bfcb0024daa778c1850bba9de94a2d1ec6a69",
            "Content-Type": "application/json"
        }
        print(payload)
        response = requests.request("POST", Blend_SMS_url + "/send", json=payload, headers=headers)

        print(response.text)   
            
def post_cold_call_communication(notion_raw_id): 
    
    #collect all information from notion DB
    user_info_df = pull_notion_data("all")
  
    #filter specific raw id for the last call
    user_info_df = user_info_df[user_info_df['notion raw id'] == notion_raw_id]

    #send process intormation if lead is interested
    if user_info_df['Lead'].values[0] == 'Interested':

        # Parse the datetime string
        date_str = user_info_df['Next Follow Up Date'].values[0]
        # First parse as full datetime with microseconds
        datetime_obj = datetime.datetime.fromisoformat(str(date_str).rstrip('Z')[:26])  # Truncate to 6 fractional digits
        date_obj = datetime_obj.date()  # Extract date part
        formatted_date = date_obj.strftime("%b %d, %Y at %H:%M")

        print(f'sending post cold call process massage')
        # format the mail
        Mail_Subject = f"Unclaimed Funds Identified for {user_info_df['home address'].values[0]} – Immediate Action Recommended"

        Mail_Content = f"""
        <html>
            <body>
                <h2>Dear {user_info_df['customer name'].values[0]} {user_info_df['customer last name'].values[0]},</h2>
                
                <p>I hope this message finds you well. I am reaching out to follow up on our recent conversation regarding <strong>surplus funds</strong> identified in your name for the property at <strong>{user_info_df['home address'].values[0]}</strong>. At <strong>True Claim Services</strong>, we specialize in assisting individuals in recovering funds left unclaimed after a foreclosure.</p>

                <p>Many individuals are unaware of their entitlement to these funds, and unfortunately, if left unclaimed, they may be forfeited to the government. Our role is to ensure you receive what is rightfully yours through a <strong>streamlined, professional, and risk-free process</strong>.</p>

                <h3>Who We Are</h3>
                <p><strong>True Claim Services</strong> is a trusted firm dedicated to helping individuals recover surplus funds efficiently and legally. With our expertise, we have successfully assisted numerous clients in reclaiming their rightful funds with <strong>no upfront costs or risks</strong>.</p>

                <h3>Our Process</h3>
                <ul>
                    <li>✔ <strong>Verification:</strong> We confirm the availability and legitimacy of your unclaimed funds.</li>
                    <li>✔ <strong>Legal Processing:</strong> Our team manages all required paperwork and filings.</li>
                    <li>✔ <strong>Successful Recovery:</strong> Upon approval, the funds are released directly to you.</li>
                </ul>

                <p>🕒 <strong>Time-Sensitive Notice</strong>: Surplus fund claims are subject to strict deadlines. Taking action promptly is crucial to ensuring you receive your funds before they are forfeited.</p>

                <h3>Why Choose True Claim Services?</h3>
                <ul>
                    <li>✔ <strong>No Upfront Fees</strong> – We operate on a contingency basis, meaning we only get paid when your claim is successfully processed.</li>
                    <li>✔ <strong>Legal Expertise</strong> – Our team of professionals handles all necessary documentation and legal procedures on your behalf.</li>
                    <li>✔ <strong>Efficient & Secure Process</strong> – We ensure a smooth and expedited claim process with minimal effort required on your part.</li>
                </ul>

                <h3>Next Step: Consultation with a Senior Surplus Funds Consultant</h3>
                <p>Your follow-up call has been scheduled for: {formatted_date}</p>

                <p>During this consultation, we will provide a <strong>detailed overview of your claim, explain the recovery process, and outline the required steps</strong> to ensure a successful outcome.</p>

                <h4>📞 Contact Us:</h4>
                <ul>
                    <li>📞 <strong>Call or Text</strong>: +1 336-360-3640</li>
                    <li>📧 <strong>Email</strong>: Info@TrueClaim.org</li>
                    <li>🌐 <strong>Website</strong>: <a href="https://trueclaim.org/">TrueClaim.org</a></li>
                </ul>

                <p>We look forward to assisting you in recovering the funds associated with <strong>{user_info_df['home address'].values[0]}</strong>. Please feel free to reach out with any questions.</p>

                <p><strong>Best regards,</strong><br>
                {Agent_name} Ronbison<br>
                Junior Surplus Funds Consultant<br>
                <strong>True Claim Services</strong></p>
            </body>
        </html>
        """
        # send the mail 
        send_mail(Mail_Subject, Mail_Content, user_info_df)


    elif user_info_df['Lead'].values[0] == 'Not interested':
        #send not interested campeign                   
        pass
        
    elif user_info_df['Lead'].values[0] == 'Did not answered':
        
        # send checking SMS:
        Content = f"Hi, is this {user_info_df['customer name'].values[0].lower()}?" 
        send_SMS(Content, user_info_df)
                
def post_closer_call_communication(notion_raw_id): 
    
    #collect all information from notion DB
    user_info_df = pull_notion_data("all")
  
    #filter specific raw id for the last call
    user_info_df = user_info_df[user_info_df['notion raw id'] == notion_raw_id]

    #send process intormation if lead is interested
    if user_info_df['Lead'].values[0] == 'Documents sent for signiture':

        print(f'sending documentation for signuture')
        # format the mail
        Mail_Subject = f"True Claim Services documentation for {user_info_df['customer name'].values[0]} {user_info_df['customer last name'].values[0]}"
    
        Mail_Content = f"""
        <html>
            <body>
                <h1>Hello!</h1>
                <p>please sign for money!!!!! :).</p>   
                <p>love you :)</p>    
    
            </body>
        </html>
        """
        # send the mail 
        send_mail(Mail_Subject, Mail_Content, user_info_df)


    elif user_info_df['Lead'].values[0] == 'Not interested':
        #send not interested campeign                   
        pass
        
def refresh_access_token(refresh_token, client_id, client_secret):
    """
    Get a new access token using the refresh token
    """
    token_url = "https://accounts.zoho.com/oauth/v2/token"
    
    data = {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token"
    }
    
    response = requests.post(token_url, data=data).json()
    return response["access_token"]

def call_setup(row, Customer_phone_number, type=""):     
               
    Customer_name = row['customer name']
    Home_address = row['home address']
    notion_raw_id = row['notion raw id']  
    First_call_Summery  = row['cold call summary']    
        
                  
    headers = {
        'Authorization': BLEND_API_KEY,
        "Content-Type": "application/json"
    }
        
        
    if type == "cold":             

        data = {
            "phone_number": Customer_phone_number,
            "from": System_phone_number,
            "task": "",
            "model": "turbo",
            "language": "en-US",
            "voice": Cold_Agent_voice,
            "voice_settings": {},
            "pathway_id": COLD_CALL_SCRIPT,
            "local_dialing": False,
            "max_duration": "12",
            "answered_by_enabled": False,
            "wait_for_greeting": True,
            "noise_cancellation": False,
            "ignore_button_press": True,
            "block_interruptions": True,
            "record": False,
            "amd": False,
            "voicemail_action": "leave_message",
            "voicemail_message": f"Hello {Customer_name}, this is {Agent_name} from True Claim Services. I'm reaching out to inform you that you might be eligible for surplus funds from a recent foreclosure. If you're interested in learning more and possibly recovering these funds, please call us back at 336 360 3640 or visit our website at Trueclaim.org. Thank you, and have a great day!",
            "record": True,
            "interruption_threshold": Interruption_Threshold_in_ms,
            "temperature": LLM_temperature,
            "transfer_list": {},
            "pronunciation_guide": [],
            "request_data": {
            "customer name": Customer_name,
            "home address": Home_address,
            "agent name": Agent_name,
            },
            "dynamic_data": [],
            "analysis_schema": {},
            "calendly": {},
            "timezone": "America/New_York"
        }        
        print(f"Cold call setup is ready for {Customer_name}")       
            
    elif type == "closer":             

        data = {
            "phone_number": Customer_phone_number,
            "from": System_phone_number,
            "task": "",
            "model": "base",
            "language": "en-US",
            "voice": Closer_Agent_voice,
            "voice_settings": {},
            "pathway_id": CLOSER_CALL_SCRIPT,
            "local_dialing": False,
            "max_duration": "12",
            "answered_by_enabled": False,
            "wait_for_greeting": True,
            "noise_cancellation": False,
            "ignore_button_press": True,
            "record": False,
            "amd": False,
            "record": True,
            "voicemail_action": "leave_message",
            "voicemail_message": f"Hello {Customer_name}, this is {Specialist_name} from True Claim Services. I have tryied to reach you to go over your claim process. please call us back at 336 360 3640 or visit our website at Trueclaim.org. Thank you, and have a great day!",
            "interruption_threshold": Interruption_Threshold_in_ms,
            "voicemail_message": "test",
            "temperature": LLM_temperature,
            "transfer_list": {},
            "pronunciation_guide": [],
            "request_data": {
            "customer name": Customer_name,
            "home address": Home_address,
            "agent name": Agent_name,
            "specialist name": Specialist_name,
            "first call summary": First_call_Summery
            },
            "dynamic_data": [],
            "analysis_schema": {},
            "calendly": {},
            "timezone": "America/New_York"
        }          
        print(f"closer call setup is ready for {Customer_name} ")               
   
    else:          
        data = {}        
        print("unkknown setup, please try again")    
                    
    return data, headers            
            
            
            
            
            

# %% [markdown]
# cold call Main loop

# %%

#collect relevent lead list
cold_call_df = pull_notion_data("cold")

cold_call_df['Continue_calling'] = "Yes"

phone_index = 5 

#initiate dict of all calls id, and cooresponding notion id like {notion id1:call id1, notion id2:call id2}
cold_call_ids = {}

#logging
logger.info(f"Successfully pulled {len(cold_call_df)} records from Notion")
print(f"Successfully pulled {len(cold_call_df)} records from Notion")

for i in range(phone_index):
# iterate rows and collect user data

    #initiate call i dlist for checking if there is need to continue calling
    check_call_ids = []
    
    for index, row in cold_call_df.iterrows():

        if len(row['Phone'].split(",")) > i and row['Continue_calling'] == "Yes":
            
            #collect first phone number for now
            Customer_phone_number = row['Phone'].split(",")[i]
                
            logger.info(f"Calling {Customer_phone_number}")
            print(f"Calling {Customer_phone_number}")
            #call setup
            data, headers = call_setup(row,Customer_phone_number,type="cold")
            # send call
            send_call_response = json.loads(requests.request("POST", Blend_url, json=data, headers=headers).text)

            # log status
            print(send_call_response)
            logger.info(send_call_response)
            
            # collect notion id and row call  id
            cold_call_ids[row['notion raw id']] = send_call_response["call_id"]
            check_call_ids.append(send_call_response["call_id"])
        
        else:
            pass

    Active_calls_count = json.loads(requests.request("GET", Blend_url, headers=headers,params={"completed":"false"}).text)['total_count']    
    
    while(Active_calls_count > 0 ):
        print(f"waiting for {Active_calls_count} calls to end")
        time.sleep(2)
        Active_calls_count = json.loads(requests.request("GET", Blend_url, headers=headers,params={"completed":"false"}).text)['total_count']  
    #wait for all tags to get updated    
    time.sleep(30)    
    
    
    for call_id_check in check_call_ids:
        # call api to get call tagges
        call_id_response = json.loads(requests.request("GET", Blend_url+"/"+call_id_check, headers=headers).text)
        # check if customer answerd and intersted so we wont call him again
        if "interested" in call_id_response["pathway_tags"] and "Answered" in call_id_response["pathway_tags"]:
            cold_call_df.loc[cold_call_df['notion raw id'] == call_id_check, 'Continue_calling'] = 'No'
            
        else:
            pass    
    
# update database based on results
for ids in cold_call_ids.keys():
    # update database based on results
    call_id = cold_call_ids[ids]
    notion_row_id = ids
    
    update_data_base_after_cold_call(notion_row_id,call_id)
    print(f"Update databsae for row: {notion_row_id} according to call: {call_id}")
    logger.info(f"Update databsae for row: {notion_row_id} according to call: {call_id}")
    # send correct mail
    post_cold_call_communication(notion_row_id)
    print(f"Sending communcation to notion row: {notion_row_id}")
    logger.info(f"Update databsae for row: {notion_row_id} according to call: {call_id}")     
    