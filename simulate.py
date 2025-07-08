# simulate.py
# This script reads from 'game_data.json' and runs the DPS simulation.
import itertools
import random
from collections import deque
import concurrent.futures
import os
import sys
import json
from typing import List, Dict, Tuple, Iterator

# --- Simulation Constants & Data (Loaded from file) ---
ABILITY_CAST_TIME, ABILITY_COOLDOWN, WEAPON_SWAP_TIME = 0.5, 3.0, 1.0
WEAPONS = {
    "Calibrum": {"name": "Calibrum", "moonlight": 50, "on_hit_effect": {"consumes_mark": True, "mark_consume_bonus_damage_flat": 15, "mark_consume_bonus_damage_bonus_ad_ratio": 0.20}, "ability": {"name": "Moonshot", "cost": 10, "base_damage": 160, "bonus_ad_ratio": 0.60, "applies_mark": True}},
    "Severum": {"name": "Severum", "moonlight": 50, "ability": {"name": "Onslaught", "cost": 10, "num_attacks_base": 6, "num_attacks_bonus_as_ratio": 2.0, "attack_base_damage": 40, "attack_bonus_ad_ratio": 0.40}},
    "Gravitum": {"name": "Gravitum", "moonlight": 50, "ability": {"name": "Binding Eclipse", "cost": 10, "base_damage": 140, "bonus_ad_ratio": 0.50, "damage_type": "magic"}},
    "Infernum": {"name": "Infernum", "moonlight": 50, "passive_effect": {"primary_target_damage_mod": 1.1}, "on_hit_effect": {"cone_secondary_target_damage_ratio": 1.0}, "ability": {"name": "Duskwave", "cost": 10, "base_damage": 65, "bonus_ad_ratio": 0.80, "triggers_off_hand_attacks": True}},
    "Crescendum": {"name": "Crescendum", "moonlight": 50, "passive_effect": {"max_chakrams": 20, "chakram_duration": 5, "bonus_damage_per_chakram_stack_ad_ratio": 0.06925}, "ability": {"name": "Sentry", "cost": 10, "generates_spectral_chakram_on_cast": True}}
}
ITEM_CONSTRAINTS = {"last_whisper": {"items": ["Lord Dominik's Regards", "Serylda's Grudge", "Mortal Reminder"], "max": 1}, "lifeline": {"items": ["Immortal Shieldbow", "Maw of Malmortius", "Sterak's Gage"], "max": 1}}

# --- Utility Functions ---
def is_valid_build(combo: Tuple[str, ...]) -> bool:
    for constraint_group in ITEM_CONSTRAINTS.values():
        if sum(1 for item in combo if item in constraint_group["items"]) > constraint_group["max"]: return False
    return True

def apply_physical_mitigation(damage: float, armor: float, pen_percent: float = 0.0, lethality: float = 0.0) -> float:
    final_armor = (armor * (1.0 - pen_percent)) - lethality
    return damage * (100.0 / (100.0 + final_armor) if final_armor >= 0 else 2.0 - (100.0 / (100.0 - final_armor)))

def apply_magic_mitigation(damage: float, mr: float) -> float:
    return damage * (100.0 / (100.0 + mr) if mr >= 0 else 2.0 - (100.0 / (100.0 - mr)))

def chunkify(iterable: Iterator, size: int) -> Iterator[Tuple]:
    it = iter(iterable)
    return iter(lambda: tuple(itertools.islice(it, size)), ())

# --- Aphelios Simulation Engine ---
class ApheliosSimulator:
    def __init__(self, items, simple_items_data, aphelios_stats_data, base_ad_lvl_18, enemy_armor, enemy_mr):
        self.item_names, self.aphelios_stats_data, self.base_ad_lvl_18 = items, aphelios_stats_data, base_ad_lvl_18
        self.item_objects_data = [simple_items_data[name] for name in items if name in simple_items_data]
        self.stats = self._calculate_initial_stats()
        self.enemy_armor, self.enemy_mr = float(enemy_armor), float(enemy_mr)
        self.weapon_queue = deque(list(WEAPONS.keys())); self.main_hand_name, self.off_hand_name = self.weapon_queue[0], self.weapon_queue[1]
        self.weapon_ammo = {w: 50 for w in WEAPONS}; self.time, self.ability_cd_ts, self.attack_counter = 0.0, 0.0, 0
        self.spellblade_ready, self.marked_target = False, False; self.chakram_stacks, self.chakram_decay_ts = 0, 0.0

    def _calculate_initial_stats(self) -> Dict[str, float]:
        stats = {"BonusAD": 30, "BonusAS_percent": 54.0, "Crit": 0.0, "CritDmg": 1.75, "Lethality": 33.0, "ArmorPen_percent": 0.0}
        for item_data in self.item_objects_data:
            item_stats = item_data.get('stats', {}) # Safely get the stats dict
            stats["BonusAD"] += item_stats.get('attack_damage', 0.0)
            stats["BonusAS_percent"] += item_stats.get('percent_attack_speed', 0.0)
            stats["Crit"] += item_stats.get('critical_strike_chance', 0.0)
            stats["Lethality"] += item_stats.get('lethality', 0.0)
            stats["ArmorPen_percent"] = max(stats["ArmorPen_percent"], item_stats.get('percent_armor_penetration', 0.0))
        if "Infinity Edge" in self.item_names: stats["CritDmg"] += 0.40
        stats["TotalAD"] = self.base_ad_lvl_18 + stats["BonusAD"]
        stats["TotalAS"] = min(2.5, self.aphelios_stats_data['attack_speed'] * (1 + (stats["BonusAS_percent"] / 100)))
        stats["Crit"] = min(1.0, stats["Crit"])
        return stats

    def rotate_weapon(self):
        self.time += WEAPON_SWAP_TIME; exhausted = self.weapon_queue.popleft(); self.weapon_queue.append(exhausted)
        self.weapon_ammo[exhausted] = WEAPONS[exhausted]["moonlight"]; self.main_hand_name, self.off_hand_name = self.weapon_queue[0], self.weapon_queue[1]

    def calculate_dps(self, duration: int = 60) -> float:
        total_damage = 0.0
        while self.time < duration:
            if self.weapon_ammo[self.main_hand_name] <= 0: self.rotate_weapon()
            if self.time >= duration: break
            if self.time >= self.ability_cd_ts and self.weapon_ammo[self.main_hand_name] >= WEAPONS[self.main_hand_name]["ability"].get("cost", 10):
                total_damage += self.simulate_ability(); self.time += ABILITY_CAST_TIME; self.ability_cd_ts = self.time + ABILITY_COOLDOWN; self.spellblade_ready = True
            else:
                total_damage += self.simulate_attack(); self.time += 1.0 / self.stats["TotalAS"]
        return total_damage / duration if duration > 0 else 0

    def simulate_attack(self) -> float:
        main_weapon = WEAPONS[self.main_hand_name]; self.weapon_ammo[self.main_hand_name] -= 1; self.attack_counter += 1
        phys_dmg, magic_dmg, true_dmg, base_dmg = 0.0, 0.0, 0.0, self.stats["TotalAD"]
        if main_weapon["name"] == "Infernum": base_dmg *= main_weapon["passive_effect"]["primary_target_damage_mod"]
        if main_weapon["name"] == "Crescendum":
            if self.time > self.chakram_decay_ts: self.chakram_stacks = 0
            base_dmg += (self.chakram_stacks * main_weapon["passive_effect"]["bonus_damage_per_chakram_stack_ad_ratio"]) * self.stats["BonusAD"]
            self.chakram_stacks = min(20, self.chakram_stacks + 1); self.chakram_decay_ts = self.time + main_weapon["passive_effect"]["chakram_duration"]
        if random.random() < self.stats["Crit"]: base_dmg *= self.stats["CritDmg"]
        phys_dmg += base_dmg
        if self.spellblade_ready and "Trinity Force" in self.item_names: phys_dmg += 2.0 * self.aphelios_stats_data['attack_damage']; self.spellblade_ready = False
        if "Kraken Slayer" in self.item_names and self.attack_counter % 3 == 0: true_dmg += 140 + (0.35 * self.stats["BonusAD"])
        if main_weapon["name"] == "Infernum": phys_dmg += base_dmg * main_weapon["on_hit_effect"]["cone_secondary_target_damage_ratio"]
        if self.marked_target:
            self.marked_target = False; calibrum_data = WEAPONS["Calibrum"]
            phys_dmg += calibrum_data["on_hit_effect"]["mark_consume_bonus_damage_flat"] + (self.stats["BonusAD"] * calibrum_data["on_hit_effect"]["mark_consume_bonus_damage_bonus_ad_ratio"])
        return apply_physical_mitigation(phys_dmg, self.enemy_armor, self.stats["ArmorPen_percent"]/100, self.stats["Lethality"]) + apply_magic_mitigation(magic_dmg, self.enemy_mr) + true_dmg

    def simulate_ability(self) -> float:
        main_weapon, off_hand_weapon, ability = WEAPONS[self.main_hand_name], WEAPONS[self.off_hand_name], main_weapon["ability"]
        self.weapon_ammo[self.main_hand_name] -= ability["cost"]; phys_dmg, magic_dmg = 0.0, 0.0
        raw_dmg = ability.get("base_damage", 0) + (self.stats["BonusAD"] * ability.get("bonus_ad_ratio", 0.0))
        if ability["name"] == "Onslaught":
            num_hits, single_hit_dmg = ability["num_attacks_base"] + int(self.stats["BonusAS_percent"] / 100 * ability["num_attacks_bonus_as_ratio"]), ability["attack_base_damage"] + self.stats["BonusAD"] * ability["attack_bonus_ad_ratio"]
            raw_dmg = single_hit_dmg * num_hits
            if off_hand_weapon["name"] == "Crescendum": self.chakram_stacks = min(20, self.chakram_stacks + (num_hits // 2))
        elif ability["name"] == "Duskwave" and ability.get("triggers_off_hand_attacks"):
            phys_dmg += self.stats["TotalAD"];
            if off_hand_weapon["name"] == "Crescendum": self.chakram_stacks = min(20, self.chakram_stacks + 3)
        elif ability["name"] == "Sentry" and ability.get("generates_spectral_chakram_on_cast"): self.chakram_stacks = min(20, self.chakram_stacks + 1)
        elif ability["name"] == "Moonshot" and ability.get("applies_mark"): self.marked_target = True
        if ability.get("damage_type") == "magic": magic_dmg += raw_dmg
        else: phys_dmg += raw_dmg
        return apply_physical_mitigation(phys_dmg, self.enemy_armor, self.stats["ArmorPen_percent"]/100, self.stats["Lethality"]) + apply_magic_mitigation(magic_dmg, self.enemy_mr)

# --- Multiprocessing and Orchestration ---
def simulate_build_chunk(args: Tuple) -> List[Tuple[Tuple[str, ...], float]]:
    builds_chunk, simple_items, aphelios_stats, base_ad_18, duration, armor, mr = args
    return [(combo, ApheliosSimulator(combo, simple_items, aphelios_stats, base_ad_18, enemy_armor=armor, enemy_mr=mr).calculate_dps(duration)) for combo in builds_chunk]

def optimize_aphelios_build(simple_items, aphelios_stats, base_ad_18, sim_duration, enemy_armor, enemy_mr, chunk_size=500):
    valid_combos_iterator = (combo for combo in itertools.combinations(list(simple_items.keys()), 5) if is_valid_build(combo))
    chunks = list(chunkify(valid_combos_iterator, chunk_size))
    if not chunks: print("No valid item combinations found after filtering."); return []
    tasks = [(chunk, simple_items, aphelios_stats, base_ad_18, sim_duration, enemy_armor, enemy_mr) for chunk in chunks]; all_results = []
    print(f"Testing {sum(len(c) for c in chunks)} valid builds in {len(chunks)} chunks...")
    with concurrent.futures.ProcessPoolExecutor() as executor:
        for i, result_chunk in enumerate(executor.map(simulate_build_chunk, tasks)):
            all_results.extend(result_chunk); print(f"  > Chunk {i+1}/{len(chunks)} completed...")
    return sorted(all_results, key=lambda x: x[1], reverse=True)

# ============================================================
# Main Execution Block
# ============================================================
def main():
    """Main function to orchestrate the entire process."""
    print("--- Aphelios Build Optimizer ---")
    
    try:
        with open("game_data.json", "r") as f:
            game_data = json.load(f)
        loaded_items, loaded_aphelios_stats, loaded_base_ad_18 = game_data["items"], game_data["aphelios_stats"], game_data["aphelios_base_ad_18"]
        print(f"\n[INFO] Successfully loaded cached game data for patch {game_data['patch']}.")
        print("[INFO] To update, run 'python fetch_data.py'.")
    except FileNotFoundError:
        print("\n[ERROR] 'game_data.json' not found! Please run 'python fetch_data.py' first.")
        sys.exit(1)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"\n[ERROR] 'game_data.json' is corrupted or invalid: {e}. Please delete it and run 'python fetch_data.py' again.")
        sys.exit(1)

    print("\n[SIMULATION] Starting Aphelios build optimization. This may take a few minutes...")
    duration_val, enemy_armor_val, enemy_mr_val = 60, 150, 75
    top_builds = optimize_aphelios_build(loaded_items, loaded_aphelios_stats, loaded_base_ad_18, duration_val, enemy_armor_val, enemy_mr_val, chunk_size=500)

    print("\n" + "="*60, f"--- Top 10 Aphelios Builds vs Target ({enemy_armor_val} Armor, {enemy_mr_val} MR) ---", "="*60, sep="\n")
    if top_builds:
        for i, (combo, dps) in enumerate(top_builds[:10]): print(f"#{i+1: <2} | DPS: {dps:<7.2f} | Build: {', '.join(combo)}")
    else: print("No builds were successfully simulated. Check item filters or constraints.")

if __name__ == "__main__":
    main()