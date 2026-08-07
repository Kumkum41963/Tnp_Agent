from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive.file",
]

flow = InstalledAppFlow.from_client_secrets_file(
    "oauth_client.json",
    SCOPES,
)

creds = flow.run_local_server(port=0)

service = build(
    "forms",
    "v1",
    credentials=creds,
    cache_discovery=False,
)

try:
    print("Creating Google Form...")

    form = service.forms().create(
        body={
            "info": {
                "title": "OAuth Test Form"
            }
        }
    ).execute()

    print("\nSUCCESS!")
    print("Form ID :", form["formId"])
    print("Title   :", form["info"]["title"])
    print("URL     :", form["responderUri"])

except HttpError as e:
    print("\nFAILED")
    print("Status :", e.status_code)
    print("Reason :", e.reason)

    if hasattr(e, "content"):
        print(e.content.decode())