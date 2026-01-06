import hvac
from dotenv import load_dotenv
load_dotenv()

client = hvac.Client()
  
def read_secret(path: str, mount="secret"):
    try:
        resp = client.secrets.kv.v1.read_secret(
            path=path,
            mount_point=mount
        )
        return resp["data"]
    except Exception as e:
        print("❌ Error:", e)
        return {}
