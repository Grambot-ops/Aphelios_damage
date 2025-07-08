# fetch_data.py
# This script's only purpose is to fetch all relevant item and champion data from the Riot API
# and save it to a local file for the simulator to use.
import os
import sys
import json
import getpass
import re

def camel_to_snake(name: str) -> str:
    """Converts a camelCase string to snake_case."""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

# A comprehensive list of all stats an item can have in camelCase format
ALL_ITEM_STATS_CAMEL_CASE = [
    "health", "healthRegen", "mana", "manaRegen", "armor", "magicResist",
    "attackDamage", "abilityPower", "attackSpeed", "percentAttackSpeed",
    "criticalStrikeChance", "lethality", "percentArmorPenetration",
    "percentBonusArmorPenetration", "magicPenetrationFlat",
    "percentMagicPenetration", "lifeSteal", "spellVamp", "omnivamp",
    "abilityHaste", "cooldownReduction", "percentMoveSpeed", "moveSpeed"
]

def fetch_and_save_data():
    """
    Connects to the Riot API, fetches data, processes it into a simple format,
    and saves it to 'game_data.json'.
    """
    try:
        import cassiopeia as cass
    except ImportError:
        print("ERROR: 'cassiopeia' library is not installed. Please run: pip install cassiopeia")
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
        
        print(f"[API] Fetching item list for region {user_region}...")
        cass_items_raw = cass.get_items(region=user_region)
        print(f"[API] Fetched {len(cass_items_raw)} item stubs. Now fully loading each item's data...")
        
        loaded_items_list = []
        for i, item in enumerate(cass_items_raw):
            try:
                _ = item.gold.total
                loaded_items_list.append(item)
            except Exception:
                continue
            if (i + 1) % 50 == 0:
                print(f"  > Loaded data for {i + 1}/{len(cass_items_raw)} items...")
        
        print("[API] All item data fully loaded.")
        aphelios_data_raw = cass.get_champion("Aphelios", region=user_region)
        print("[API] Champion data fetched successfully.")

    except Exception as e:
        print(f"\n[ERROR] Failed to fetch data from Riot API. {type(e).__name__}: {e}")
        print("Please ensure your API key is valid and not expired.")
        sys.exit(1)

    # --- 3. Process Data into Simple Dictionaries ---
    print("\n[PROCESS] Processing and simplifying API data...")
    
    simple_items_data = {}
    for item in loaded_items_list:
        if item.gold.total > 1500 and "Mythic" not in item.description:
            item_stats = {}
            for stat_name_camel in ALL_ITEM_STATS_CAMEL_CASE:
                value = getattr(item.stats, stat_name_camel, 0.0)
                if value != 0.0: # Only store stats the item actually has
                    stat_name_snake = camel_to_snake(stat_name_camel)
                    item_stats[stat_name_snake] = value
            
            # Special handling for armor penetration which has two possible sources
            pen_value = getattr(item.stats, 'percentArmorPenetration', 0.0) or getattr(item.stats, 'percentBonusArmorPenetration', 0.0)
            if pen_value != 0.0:
                item_stats['percent_armor_penetration'] = pen_value

            simple_items_data[item.name] = {'stats': item_stats}
    
    aphelios_stats_data = {
        'attack_damage': aphelios_data_raw.stats.attackDamage,
        'attack_damage_per_level': aphelios_data_raw.stats.attackDamagePerLevel,
        'attack_speed': aphelios_data_raw.stats.attackSpeed
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