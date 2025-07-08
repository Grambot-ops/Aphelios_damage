# fetch_data.py
# This script's only purpose is to fetch data from the Riot API and save it to a local file.
import os
import sys
import json
import getpass

def fetch_and_save_data():
    """
    Connects to the Riot API using Cassiopeia, fetches item and champion data,
    processes it into a simple format, and saves it to 'game_data.json'.
    """
    try:
        import cassiopeia as cass
    except ImportError:
        print("ERROR: 'cassiopeia' library is not installed.")
        print("Please run: pip install cassiopeia")
        sys.exit(1)

    # --- 1. Get User Input for Configuration ---
    api_key = os.environ.get("RIOT_API_KEY")
    if not api_key:
        print("\n[SETUP] RIOT_API_KEY environment variable not found.")
        api_key = getpass.getpass("Please enter your Riot API Key to continue (input will be hidden): ")
        if not api_key:
            print("\nNo API key provided. Exiting.")
            sys.exit(1)
    else:
        print("\n[SETUP] Found RIOT_API_KEY in environment variable.")

    VALID_REGIONS = ["BR", "EUNE", "EUW", "JP", "KR", "LAN", "LAS", "NA", "OCE", "TR", "RU", "PH", "SG", "TH", "TW", "VN"]
    user_region = ""
    while not user_region:
        user_region_input = input(f"Please enter your server region to fetch data from (e.g., NA, EUW, KR): ").upper()
        if user_region_input in VALID_REGIONS:
            user_region = user_region_input
        else:
            print(f"Invalid region '{user_region_input}'. Please choose from: {', '.join(VALID_REGIONS)}")

    # --- 2. Configure Cassiopeia and Fetch Data ---
    try:
        print("\n[API] Configuring Cassiopeia...")
        settings = {"pipeline": {"Cache": {}, "DDragon": {}, "RiotAPI": {"api_key": api_key}}, "logging": {"print_calls": False}}
        cass.apply_settings(settings)
        
        print(f"[API] Fetching data for region {user_region}...")
        cass_items_raw = cass.get_items(region=user_region)
        aphelios_data_raw = cass.get_champion("Aphelios", region=user_region)
        print("[API] Data fetched successfully.")
    except Exception as e:
        print(f"\n[ERROR] Failed to fetch data from Riot API. {type(e).__name__}: {e}")
        print("Please ensure your API key is valid and not expired.")
        sys.exit(1)

    # --- 3. Process Data into Simple Dictionaries ---
    print("\n[PROCESS] Processing and simplifying API data...")
    simple_items_data = {
        item.name: {
            'attack_damage': item.stats.attack_damage,
            'percent_attack_speed': item.stats.percent_attack_speed,
            'critical_strike_chance': item.stats.critical_strike_chance,
            'lethality': getattr(item.stats, 'lethality', 0.0),
            'percent_armor_penetration': getattr(item.stats, 'percent_armor_penetration', 0.0) or getattr(item.stats, 'percent_bonus_armor_penetration', 0.0)
        }
        for item in cass_items_raw if item.in_store and item.gold.total > 1500 and "Mythic" not in item.description and "Support" not in item.tags
    }
    
    aphelios_stats_data = {
        'attack_damage': aphelios_data_raw.stats.attack_damage,
        'attack_damage_per_level': aphelios_data_raw.stats.attack_damage_per_level,
        'attack_speed': aphelios_data_raw.stats.attack_speed
    }
    
    level_ups = 17
    growth_multiplier = level_ups * (0.7025 + 0.0175 * level_ups)
    base_ad_lvl_18 = aphelios_stats_data['attack_damage'] + (aphelios_stats_data['attack_damage_per_level'] * growth_multiplier)
    
    # --- 4. Package and Save Data to JSON File ---
    packaged_data = {
        "patch": aphelios_data_raw.version,
        "items": simple_items_data,
        "aphelios_stats": aphelios_stats_data,
        "aphelios_base_ad_18": base_ad_lvl_18
    }

    try:
        with open("game_data.json", "w") as f:
            json.dump(packaged_data, f, indent=4)
        print(f"\n[SUCCESS] Successfully saved game data for patch {packaged_data['patch']} to 'game_data.json'.")
        print("You can now run 'simulate.py' to perform the calculations.")
    except IOError as e:
        print(f"\n[ERROR] Could not write to 'game_data.json'. Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    fetch_and_save_data()