# import os
# from supabase import create_client, Client
# from dotenv import load_dotenv
# from pathlib import Path

# load_dotenv()

# # Supabase sozlamalari
# SUPABASE_URL = os.environ.get("SUPABASE_URL")
# SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
# SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
# API_ID = os.environ["API_ID"]
# API_HASH = os.environ["API_HASH"]
# # src/config.py ichida:
# print("API_ID:", os.environ.get("API_ID"))
# print("API_HASH:", os.environ.get("API_HASH"))


# SESS_ROOT = Path("sessions")
# PENDING_FILE = "pending.json"

# # Supabase klientini yaratish
# supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
# supabase_service: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
# print("Supabase client created successfully.")
# api_id = API_ID
# api_hash = API_HASH



import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BASE_URL = os.environ.get("BASE_URL", "https://talkapp.up.railway.app")

# Polar payment configuration
POLAR_ACCESS_TOKEN = os.environ.get("POLAR_ACCESS_TOKEN")
POLAR_SUCCESS_URL = os.environ.get("POLAR_SUCCESS_URL")

SESS_ROOT = Path("sessions")
SESS_ROOT.mkdir(parents=True, exist_ok=True)

PENDING_FILE = "pending.json"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
supabase_service: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

print("Supabase client created successfully.")