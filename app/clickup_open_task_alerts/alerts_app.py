# This script filters out old pending ClickUp tasks and sends them as a formatted message to a Slack channel.
from config import LISTS, AGE_THRESHOLD_DAYS, STATUSES, CHANNEL_NAME, HEADER_VARIABLE
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
import slack
import requests
import boto3
import json
import logging
from botocore.exceptions import ClientError

def get_secret(secret_name, region_name="ap-south-1"):
    try:
        client = boto3.session.Session().client(
            service_name='secretsmanager', region_name=region_name
        )
        secret_value = client.get_secret_value(SecretId=secret_name)
        return json.loads(secret_value['SecretString'])
    except ClientError as e:
        logging.exception(f"Failed to get secret {secret_name}: {e}")
        raise

secrets = get_secret("my_clickup_slack_secrets")

CLICKUP_API_TOKEN = secrets["CLICKUP_API_TOKEN"]
SLACK_BOT_TOKEN = secrets["SLACK_BOT_TOKEN"]


# Set up headers for ClickUp API requests
HEADERS = {
    "Authorization": os.getenv("CLICKUP_API_TOKEN"),
    "Content-Type": "application/json"
}

# Initialize the Slack WebClient with the bot token
slack_client = slack.WebClient(token=SLACK_BOT_TOKEN)

#Set maximum character length for each Slack message
MAX_CHAR = 2800


# Fetch tasks from ClickUp for a given list ID, filtered by specified statuses
def get_filtered_tasks_for_list(list_id):
    status_query = "&".join([f"statuses[]={status.replace(' ', '%20')}" for status in STATUSES])
    url = f"https://api.clickup.com/api/v2/list/{list_id}/task?{status_query}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        print(f"Error fetching tasks for list {list_id}: {response.status_code}")
        return []
    return response.json().get("tasks", [])


# Get Slack user ID based on email address (used to @mention assignees)
def slack_user_id(email):
    response = requests.get(
        f"https://slack.com/api/users.lookupByEmail?email={email}",
        headers={
            "Authorization": f"Bearer {BOT_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    if response.status_code == 200 and response.json().get("ok"):
        return response.json()["user"]["id"]
    else:
        print(f"Slack user lookup failed for {email}: {response.text}")
        return None


# Calculate the number of days between now and the task creation date
def number_of_days(created_ts):
    created_sec = int(created_ts) / 1000
    created_date = datetime.fromtimestamp(created_sec, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = now - created_date
    return round(delta.days)


# Truncate function to Limit the title within the column width
def truncate(text, width):
    return text if len(text) <= width else text[:width - 3] + "..."


# Function to send a Slack message 
def send_message_to_slack(text, list_name=None):
    response = slack_client.chat_postMessage(channel=CHANNEL_NAME, text=text)
    if not response["ok"]:
        print("Slack message failed:", response["error"])
    else:
        if list_name:
            print(f"Slack message sent successfully for {list_name} list.")
        else:
            print("✅ Slack message sent successfully.")


# Track whether any message was actually sent
any_message_sent = False

# Loop through each ClickUp list
for list_id, list_name in LISTS.items():
    tasks = get_filtered_tasks_for_list(list_id)
    
    if not tasks:
        print(f"No open tasks found in {list_name}.")
        continue

    rows = []
    has_old_task = False # This variable helps to determine if a list has tasks older than threshold

    # Loop through each task in the list
    for task in tasks:
        created = task.get("date_created", 0)
        duration_days = number_of_days(created) if created else 0

        # Skip tasks that are not older than the threshold
        if duration_days <= AGE_THRESHOLD_DAYS:
            continue  # skip recent tasks

        has_old_task = True

        duration = f"{duration_days} days"
        creator = task.get("creator", {}).get("username", "Unknown")
        custom_id = task.get("custom_id", task["id"])
        task_url = task.get("url", "")
        clickable_id = f"<{task_url}|{custom_id}>"
        title = task.get("name", "")
        status = task.get("status", {}).get("status", "Unknown")

        # Get all assignees and map to Slack mentions
        assignee_list = task.get("assignees", [])
        assignee_mentions = []
        for assignee in assignee_list:
            email = assignee.get("email")
            name = assignee.get("username", "Unknown")
            slack_id = slack_user_id(email) if email else None
            assignee_mentions.append(f"<@{slack_id}>" if slack_id else email or name)
        assignees_str = ", ".join(assignee_mentions) if assignee_mentions else "Unassigned"

         # Format task row
        task_row = (
            f"{clickable_id} | "
            f"{truncate(title, 50):<50} | "
            f"{duration:<10} | "
            f"{creator:<20} | "
            f"{status:<20} | "
            f"{assignees_str}\n"
        )
        rows.append(task_row)

    # If there were no old tasks in this list, skip sending message
    if not has_old_task:
        print(f"No tasks older than {AGE_THRESHOLD_DAYS} days in {list_name}.")
        continue

    # Prepare message header and base label
    table_header = (
        f"{'ClickUpID'}| {'Title':<50} | {'Duration':<10} | {'Created By':<20} | {'Status':<20} | Assignees"
        f"\n{'-' * 150}\n"
    )
    heading_base = f"🚨 *Below are the ClickUp Tickets in {list_name} Open for Over {HEADER_VARIABLE}* 🚨\n\n"

    # Split messages into chunks if exceeding Slack message length limit
    chunk = ""
    chunk_count = 1

    for task_row in rows:
        if len(chunk) + len(task_row) + len(table_header) > MAX_CHAR:
            header_label = f"📂 *{list_name}*" if chunk_count == 1 else f"📂 *{list_name} (continued)*"
            message = f"{heading_base}{header_label}\n```{table_header}{chunk}```"
            send_message_to_slack(message, list_name)
            chunk = task_row + "\n"
            chunk_count += 1
        else:
            chunk += task_row + "\n"

    # Send the final chunk
    if chunk:
        header_label = f"📂 *{list_name}*" if chunk_count == 1 else f"📂 *{list_name} (continued)*"
        message = f"{heading_base}{header_label}\n```{table_header}{chunk}```"
        send_message_to_slack(message, list_name)

    any_message_sent = True  # At least one Slack message was sent

# Send a horizontal separator if anything was posted
if any_message_sent:
    send_message_to_slack("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
