import itertools
import random
from collections import deque
import functools
import concurrent.futures
import os
import sys

# ============================================================
# Pre-flight Check: Ensure Cassiopeia is installed
# ============================================================
try:
    import cassiopeia as cass
except ImportError:
    python_executable = sys.executable
    print("="*60, "\nERROR: Required library 'cassiopeia' is not installed.",
          "\nPlease install it by running the following command in your terminal:",
          f"\n    {python_executable} -m pip install cassiopeia\n", "="*60, sep="\n")
    sys.exit(1)

# ============================================================
# Aphelios Simulation Code - Final Version
# ============================================================

# --- Globals, Constants, and Classes ---
CASSIOPEIA_ITEMS, APHELIOS_DATA, BASE_AD_LVL_18 = {}, None, 0
INNATE_BONUS_AD, INNATE_BONUS_AS_PERCENT, INNATE_LETHALITY = 30, 54.0, 33.0
ABILITY_CAST_TIME, ABILITY_COOLDOWN, WEAPON_SWAP_TIME = 0.5, 3.0, 1.0
class MoonstoneWeapon:
    def __init__(self, name, moonlight, passive_effect=None, on_hit_effect=None, ability_details=None):
        self.name, self.moonlight, self.passive_effect, self.on_hit_effect, self.ability_details = name, moonlight, passive_effect or {}, on_hit_effect or {}, ability_details or {}
WEAPONS = { "Calibrum": MoonstoneWeapon(name="Calibrum", moonlight=50, passive_effect={"bonus_range": 100}, on_hit_effect={"consumes_mark": True, "mark_consume_bonus_damage_flat": 15, "mark_consume_bonus_damage_bonus_ad_ratio": 0.20, "mark_special_range": 1800}, ability_details={"name": "Moonshot", "cost": 10, "base_damage_lvl18": 160, "bonus_ad_ratio": 0.60, "ap_ratio": 1.0, "applies_mark": True, "mark_duration": 4.5}), "Severum": MoonstoneWeapon(name="Severum", moonlight=50, passive_effect={"heal_from_damage_ratio_lvl18": 0.071, "ability_heal_from_damage_ratio_lvl18": 0.1775, "uncancellable_windup": True}, ability_details={"name": "Onslaught", "cost": 10, "duration": 1.75, "bonus_ms_flat": 0.20, "num_attacks_base": 6, "num_attacks_bonus_as_ratio": 2, "attack_base_damage_lvl18": 40, "attack_bonus_ad_ratio": 0.40, "on_hit_effectiveness": 0.25}), "Gravitum": MoonstoneWeapon(name="Gravitum", moonlight=50, on_hit_effect={"slow_amount": 0.30, "slow_duration": 2.5}, ability_details={"name": "Binding Eclipse", "cost": 10, "base_damage_lvl18": 140, "bonus_ad_ratio": 0.50, "ap_ratio": 0.7, "root_duration": 1.0, "damage_type": "magic"}), "Infernum": MoonstoneWeapon(name="Infernum", moonlight=50, passive_effect={"primary_target_damage_mod": 1.1}, on_hit_effect={"cone_secondary_target_damage_ratio_lvl18": 1.0, "cone_secondary_target_minion_damage_ratio_lvl18": 0.30}, ability_details={"name": "Duskwave", "cost": 10, "base_damage_lvl18": 65, "bonus_ad_ratio": 0.80, "ap_ratio": 0.7, "triggers_off_hand_attacks": True}), "Crescendum": MoonstoneWeapon(name="Crescendum", moonlight=50, passive_effect={"max_chakrams": 20, "chakram_duration": 5, "bonus_damage_per_chakram_stack_ratio": 0.06925}, ability_details={"name": "Sentry", "cost": 10, "generates_spectral_chakram_on_cast": True})}
ITEM_CONSTRAINTS = {"last_whisper": {"items": ["Lord Dominik's Regards", "Serylda's Grudge", "Mortal Reminder", "Black Cleaver"], "max": 1}, "lifeline": {"items": ["Immortal Shieldbow", "Maw of Malmortius", "Sterak's Gage"], "max": 1}}
def load_cassiopeia_data(region="NA"):
    global CASSIOPEIA_ITEMS, APHELIOS_DATA, BASE_AD_LVL_18
    print("Loading live game data from Riot API via Cassiopeia...")
    cass_items = cass.get_items(region=region)
    CASSIOPEIA_ITEMS = {item.name: item for item in cass_items if item.in_store and "Mythic" not in item.description}
    APHELIOS_DATA = cass.get_champion("Aphelios", region=region)
    level_ups, growth_multiplier = 17, 17 * (0.7025 + 0.0175 * 17)
    BASE_AD_LVL_18 = APHELIOS_DATA.stats.attack_damage + (APHELIOS_DATA.stats.attack_damage_per_level * growth_multiplier)
    print(f"Data loaded. Found {len(CASSIOPEIA_ITEMS)} valid items. Aphelios Level 18 Base AD: {BASE_AD_LVL_18:.2f}")
def is_valid_build(combo):
    for constraint_group in ITEM_CONSTRAINTS.values():
        if sum(1 for item in combo if item in constraint_group["items"]) > constraint_group["max"]: return False
    return True
def apply_physical_mitigation(damage, enemy_armor, armor_pen_percent=0.0, lethality=0.0):
    final_armor = (enemy_armor * (1.0 - armor_pen_percent)) - lethality
    return damage * (100.0 / (100.0 + final_armor) if final_armor >= 0 else 2.0 - (100.0 / (100.0 - final_armor)))
def apply_magic_mitigation(damage, enemy_mr):
    return damage * (100 / (100 + enemy_mr) if enemy_mr >= 0 else 2 - (100 / (100 - enemy_mr)))
def chunkify(iterable, chunk_size):
    for i in range(0, len(iterable), chunk_size): yield iterable[i:i + chunk_size]
class ApheliosSimulator:
    def __init__(self, items, enemy_armor=250.0, enemy_health=3500.0, enemy_mr=50.0):
        self.item_names, self.cass_item_objects, self.stats = items, [CASSIOPEIA_ITEMS[name] for name in items if name in CASSIOPEIA_ITEMS], self._calculate_initial_stats()
        self.enemy_armor, self.enemy_health, self.enemy_mr = float(enemy_armor), float(enemy_health), float(enemy_mr)
        self.weapon_queue, self.main_hand_name, self.off_hand_name = deque(["Calibrum", "Severum", "Gravitum", "Infernum", "Crescendum"]), "Calibrum", "Severum"
        self.weapon_ammo, self.time, self.ability_cooldown_timestamp, self.chakram_stacks, self.attack_counter, self.spellblade_ready = {w: 50 for w in WEAPONS}, 0.0, 0.0, 0, 0, False
    @functools.lru_cache(maxsize=1)
    def _calculate_initial_stats(self):
        stats = {"BonusAD": INNATE_BONUS_AD, "BonusAS_percent": INNATE_BONUS_AS_PERCENT, "Crit": 0.0, "CritDmg": APHELIOS_DATA.stats.critical_strike_damage, "Lethality": INNATE_LETHALITY, "ArmorPen_percent": 0.0, "LS": 0.0, "Omnivamp": 0.0, "AttackRange": APHELIOS_DATA.stats.attack_range}
        for item in self.cass_item_objects:
            stats["BonusAD"] += item.stats.attack_damage; stats["BonusAS_percent"] += item.stats.percent_attack_speed; stats["Crit"] += item.stats.critical_strike_chance
            stats["Lethality"] += getattr(item.stats, 'lethality', 0.0); stats["LS"] += item.stats.life_steal; stats["Omnivamp"] += getattr(item.stats, 'spell_vamp', 0.0)
            stats["ArmorPen_percent"] = max(stats["ArmorPen_percent"], max(getattr(item.stats, 'percent_armor_penetration', 0.0), getattr(item.stats, 'percent_bonus_armor_penetration', 0.0)))
        if "Infinity Edge" in self.item_names: stats["CritDmg"] += 0.40
        stats["TotalAD"] = BASE_AD_LVL_18 + stats["BonusAD"]
        stats["TotalAS"] = min(2.5, APHELIOS_DATA.stats.attack_speed * (1 + (stats["BonusAS_percent"] / 100) * APHELIOS_DATA.stats.attack_speed_ratio))
        stats["Crit"] = min(1.0, stats["Crit"])
        return stats
    def rotate_weapon(self):
        self.time += WEAPON_SWAP_TIME; exhausted_name = self.weapon_queue.popleft(); self.weapon_queue.append(exhausted_name)
        self.weapon_ammo[exhausted_name], self.main_hand_name, self.off_hand_name = WEAPONS[exhausted_name].moonlight, self.weapon_queue[0], self.weapon_queue[1]
    def calculate_dps(self, duration=60):
        total_damage = 0.0
        while self.time < duration:
            if self.weapon_ammo[self.main_hand_name] <= 0: self.rotate_weapon()
            if self.time >= duration: break
            main_weapon = WEAPONS[self.main_hand_name]
            if self.time >= self.ability_cooldown_timestamp and self.weapon_ammo[self.main_hand_name] >= main_weapon.ability_details.get("cost", 10):
                total_damage += self.simulate_ability(); self.time += ABILITY_CAST_TIME; self.ability_cooldown_timestamp = self.time + ABILITY_COOLDOWN; self.spellblade_ready = True
            else:
                total_damage += self.simulate_attack(); self.time += 1.0 / self.stats["TotalAS"]
        return total_damage / duration if duration > 0 else 0
    def simulate_attack(self):
        main_weapon, self.weapon_ammo[self.main_hand_name], self.attack_counter = WEAPONS[self.main_hand_name], self.weapon_ammo[self.main_hand_name] - 1, self.attack_counter + 1
        physical_damage, magic_damage, true_damage = 0.0, 0.0, 0.0
        base_attack_damage = self.stats["TotalAD"]
        if main_weapon.name == "Infernum": base_attack_damage *= 1.1
        if main_weapon.name == "Crescendum": base_attack_damage += (self.chakram_stacks * 0.06925) * self.stats["BonusAD"]
        if random.random() < self.stats["Crit"]: base_attack_damage *= self.stats["CritDmg"]
        physical_damage += base_attack_damage
        if self.spellblade_ready and "Trinity Force" in self.item_names: physical_damage += 2.0 * APHELIOS_DATA.stats.attack_damage; self.spellblade_ready = False
        if self.attack_counter % 3 == 0 and "Kraken Slayer" in self.item_names: true_damage += 150
        if main_weapon.name == "Infernum": physical_damage += base_attack_damage * 1.0
        return apply_physical_mitigation(physical_damage, self.enemy_armor, self.stats["ArmorPen_percent"], self.stats["Lethality"]) + magic_damage + true_damage
    def simulate_ability(self):
        main_weapon, off_hand_weapon, ability_details = WEAPONS[self.main_hand_name], WEAPONS[self.off_hand_name], main_weapon.ability_details
        self.weapon_ammo[self.main_hand_name] -= 10
        physical_damage, magic_damage, raw_damage = 0.0, 0.0, ability_details.get("base_damage_lvl18", 0) + (self.stats["BonusAD"] * ability_details.get("bonus_ad_ratio", 0.0))
        if main_weapon.name == "Severum":
            num_attacks = 6 + int(self.stats["BonusAS_percent"] / 100 * 2)
            single_hit_damage, raw_damage = 40 + self.stats["BonusAD"] * 0.4, 0
            for _ in range(num_attacks):
                raw_damage += single_hit_damage
                if off_hand_weapon.name == "Crescendum": self.chakram_stacks = min(20, self.chakram_stacks + 1)
        elif main_weapon.name == "Infernum":
            if ability_details.get("triggers_off_hand_attacks") and off_hand_weapon.name == "Crescendum": self.chakram_stacks = min(20, self.chakram_stacks + 3)
            physical_damage += raw_damage
        elif main_weapon.name == "Crescendum":
            if ability_details.get("generates_spectral_chakram_on_cast"): self.chakram_stacks = min(20, self.chakram_stacks + 1)
        if ability_details.get("damage_type") == "magic": magic_damage += raw_damage
        else: physical_damage += raw_damage
        return apply_physical_mitigation(physical_damage, self.enemy_armor, self.stats["ArmorPen_percent"], self.stats["Lethality"]) + apply_magic_mitigation(magic_damage, self.enemy_mr)
def simulate_build_chunk(builds_chunk, duration, armor, health, mr):
    results = []
    for combo in builds_chunk:
        simulator = ApheliosSimulator(combo, enemy_armor=armor, enemy_health=health, enemy_mr=mr)
        results.append((combo, simulator.calculate_dps(duration)))
    return results
def optimize_aphelios_build(simulation_duration=60, enemy_armor=200, enemy_health=3000, enemy_mr=100, chunk_size=500):
    valid_combos = [combo for combo in itertools.combinations(list(CASSIOPEIA_ITEMS.keys()), 5) if is_valid_build(combo)]
    if not valid_combos: print("No valid item combinations found."); return []
    chunks, all_results = list(chunkify(valid_combos, chunk_size)), []
    print(f"Testing {len(valid_combos)} valid builds in {len(chunks)} chunks...")
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = [executor.submit(simulate_build_chunk, chunk, simulation_duration, enemy_armor, enemy_health, enemy_mr) for chunk in chunks]
        for future in concurrent.futures.as_completed(futures):
            all_results.extend(future.result())
    return sorted(all_results, key=lambda x: x[1], reverse=True)


# ============================================================
# Main Execution Block
# ============================================================
if __name__ == "__main__":
    print("--- Aphelios Build Optimizer ---")
    
    # --- Step 1: Securely get the Riot API Key ---
    api_key = os.environ.get("RIOT_API_KEY")
    if not api_key:
        print("\n[SETUP] RIOT_API_KEY environment variable not found.")
        try:
            import getpass
            api_key = getpass.getpass("Please enter your Riot API Key to continue: ")
        except (ImportError, ModuleNotFoundError):
            api_key = input("Please enter your Riot API Key to continue: ")
        if not api_key:
            print("\nNo API key provided. Exiting."); sys.exit(1)
    else:
        print("\n[SETUP] Found RIOT_API_KEY in environment variable.")
        
    # --- NEW: Step 2: Get the User's Region ---
    VALID_REGIONS = ["BR", "EUNE", "EUW", "JP", "KR", "LAN", "LAS", "NA", "OCE", "TR", "RU", "PH", "SG", "TH", "TW", "VN"]
    user_region = ""
    while user_region not in VALID_REGIONS:
        user_region = input("Please enter your server region (e.g., NA, EUW, KR): ").upper()
        if user_region not in VALID_REGIONS:
            print(f"Invalid region '{user_region}'. Please choose from: {', '.join(VALID_REGIONS)}")

    # --- Step 3: Configure Cassiopeia and Load Data ---
    try:
        print("[SETUP] Configuring Cassiopeia...")
        
        settings = {
            "global": {
                "default_region": user_region  # Use the selected region
            },
            "pipeline": {
                "Cache": {},
                "DDragon": {},
                "RiotAPI": {
                    "api_key": api_key
                }
            }
        }
        cass.apply_settings(settings)
        
        load_cassiopeia_data(region=user_region)
        
    except Exception as e:
        print(f"\n[ERROR] Failed to configure Cassiopeia or load data: {e}")
        print("Please ensure your API key is valid, not expired, and has access.")
        sys.exit(1)

    # --- Step 4: Run the Simulation ---
    print("\n[SIMULATION] Starting Aphelios build optimization...")
    duration = 60
    enemy_armor_val, enemy_health_val, enemy_mr_val = 150, 2500, 75
    
    top_builds = optimize_aphelios_build(
        simulation_duration=duration,
        enemy_armor=enemy_armor_val,
        enemy_health=enemy_health_val,
        enemy_mr=enemy_mr_val,
        chunk_size=200
    )

    # --- Step 5: Display Results ---
    print("\n--- Top 10 Aphelios Builds ---")
    if top_builds:
        for i, (combo, dps) in enumerate(top_builds[:10]):
            print(f"{i+1}. Build: {', '.join(combo)}")
            print(f"   Simulated DPS: {dps:.2f}")
    else:
        print("No builds were successfully simulated.")