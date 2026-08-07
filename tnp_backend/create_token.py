from google_auth_oauthlib.flow import InstalledAppFlow

# use this to create a token for any new oauth acc (currently for tnpofficialbtece)
SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive",
]

flow = InstalledAppFlow.from_client_secrets_file(
    "C:/Users/kumku/OneDrive/Desktop/CODING/Projects/Tnp_Auto_Agent/tnp_backend/oauth_client.json",
    SCOPES,
)

creds = flow.run_local_server(port=0)

with open("C:/Users/kumku/OneDrive/Desktop/CODING/Projects/Tnp_Auto_Agent/tnp_backend/token.json", "w") as f:
    f.write(creds.to_json())

print("token.json created successfully!")