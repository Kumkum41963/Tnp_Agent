from app.config import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SERVICE_ACCOUNT_FILE = settings.google_service_account_file

print("Credential file:", SERVICE_ACCOUNT_FILE)

SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive",
]

# Create credentials FIRST
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=SCOPES,
)

print("Service Account:", creds.service_account_email)

# ----------------------------
# Test Drive API
# ----------------------------
print("\n========== DRIVE TEST ==========")

try:
    drive = build(
        "drive",
        "v3",
        credentials=creds,
        cache_discovery=False,
    )

    files = drive.files().list(
        pageSize=5,
        fields="files(id,name,mimeType)"
    ).execute()

    print("Drive API SUCCESS")
    print(files)

except HttpError as e:
    print("\nDrive API FAILED")
    print("Status:", e.status_code)
    print("Reason:", e.reason)

    if hasattr(e, "content"):
        print(e.content.decode())


# ----------------------------
# Test Forms API
# ----------------------------
print("\n========== FORMS TEST ==========")

service = build(
    "forms",
    "v1",
    credentials=creds,
    cache_discovery=False,
)

try:
    body = {
        "info": {
            "title": "ChatGPT Test Form"
        }
    }

    print("Creating form...")

    form = service.forms().create(body=body).execute()

    print("\nSUCCESS!")
    print(form)

except HttpError as e:
    print("\nForms API FAILED")
    print("Status:", e.status_code)
    print("Reason:", e.reason)

    if hasattr(e, "content"):
        print(e.content.decode())