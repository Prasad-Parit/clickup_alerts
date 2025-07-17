# config.py

# Mapping of ClickUp List IDs to readable names
LISTS = {
    #"List_ID":"List_Name"
    "900200424416": "AWS",
    "900200424417": "GitHub",
    "901604984656": "MongoDB Atlas",
    "900200645782": "Jenkins",
    "900200667461": "Miscellaneous",  #comment
    "901608469670": "Prod Temp Access VPN",
    "901608574162": "Prod Temp Access DB"
}

# Define the statuses to filter
STATUSES = [
    "Open",
    "Waiting for support",
    "Waiting for approval",
    "On hold"
]

# Age threshold (in days) to consider tasks as stale
AGE_THRESHOLD_DAYS = 14
HEADER_VARIABLE="2 Weeks" #Used here for the message heading -> Here are ClickUp Tickets Open for Over {HEADER_VARIABLE}

#Slack Channel name to send the message
CHANNEL_NAME="#clickup-alerts"