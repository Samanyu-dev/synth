from app.config import get_settings
from app.services.sheets import _get_client
settings = get_settings()
client = _get_client()
sh = client.open_by_key("1mVpq9-Q82txDeFzwFMOhYBfpreun3jImVkwx1tVdR1s")
ws = sh.worksheet("synth_manual_entries")
print("Total rows:", ws.row_count)
print("All values:", ws.get_all_values())
