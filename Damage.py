import itertools
import random
from collections import deque
import functools
import concurrent.futures
import os

# ============================================================
# Aphelios Simulation Code - Enhanced Version
#
# This version incorporates corrections and deeper mechanics based on the provided research.txt,
# including:
#   - Corrected Lethality mechanic (flat value, not scaling with level, per V14.1 research).
#   - Inclusion of Aphelios's innate stats from his "Weapon Master" passive.
#   - More accurate damage scaling for Crescendum chakrams.
#   - Stateful simulation for item procs (e.g., Kraken Slayer, Spellblade) instead of averaging.
#   - Refined simulation of abilities like Onslaught to be more mechanically accurate.
#   - Deeper modeling of weapon synergy conditions beyond a simple multiplier.
# ============================================================

# --- Core Champion and Game Constants from Research ---
# Aphelios Level 18 Base Stats
BASE_AD_LEVEL18 = 94.1
BASE_AS = 0.64
AS_RATIO = 0.658 # AS Ratio is used for bonus attack speed scaling
DEFAULT_CRIT_DAMAGE = 1.75
BASE_HEALTH = 2334
BASE_MANA = 1062
BASE_ARMOR = 97.4
BASE_MR = 52.1
BASE_ATTACK_RANGE = 550

# Aphelios's Innate "Weapon Master" Passive Stats (at max rank, Level 18)
# Source: research.txt, "The Hitman and the Seer" section
INNATE_BONUS_AD = 30
INNATE_BONUS_AS_PERCENT = 54.0 # This is a percentage
INNATE_LETHALITY = 33.0

# Simulation Constants
ABILITY_CAST_TIME = 0.5
ABILITY_COOLDOWN = 3.0
WEAPON_SWAP_TIME = 1.0  # CORRECTED: Based on "assembles his next available weapon over 1 second" from research.

# ============================================================
# Weapon Synergy Definitions (from research)
# ============================================================
WEAPON_SYNERGIES = {
    ("Calibrum", "Severum"): {"description": "Long-range sustain", "multiplier": 1.15, "conditions": {"heal_amplifier": 1.2}},
    ("Calibrum", "Gravitum"): {"description": "Control combo", "multiplier": 1.2, "conditions": {"root_duration": 1.35}},
    ("Calibrum", "Infernum"): {"description": "AOE marking", "multiplier": 1.25, "conditions": {"mark_splash": True}},
    ("Calibrum", "Crescendum"): {"description": "Turret sniper", "multiplier": 1.3, "conditions": {"turret_range": 1800}},
    ("Severum", "Gravitum"): {"description": "Drain tank", "multiplier": 1.2, "conditions": {"heal_amplifier": 1.15}},
    ("Severum", "Infernum"): {"description": "AOE lifesteal", "multiplier": 1.3, "conditions": {"splash_healing": True}},
    ("Severum", "Crescendum"): {"description": "Chakram stacking", "multiplier": 1.35, "conditions": {"chakram_generation_onslaught": 2}},
    ("Gravitum", "Infernum"): {"description": "AOE control", "multiplier": 1.25, "conditions": {"slow_splash": True}},
    ("Gravitum", "Crescendum"): {"description": "Turret control", "multiplier": 1.2, "conditions": {"turret_slow": True}},
    ("Infernum", "Crescendum"): {"description": "AOE chakrams", "multiplier": 1.4, "conditions": {"splash_chakram_gen": True}}
}

# ============================================================
# Weapon Definitions (Enhanced with research data)
# ============================================================
class MoonstoneWeapon:
    def __init__(self, name, moonlight, passive_effect=None, on_hit_effect=None, ability_details=None):
        self.name = name
        self.moonlight = moonlight
        self.passive_effect = passive_effect or {}
        self.on_hit_effect = on_hit_effect or {}
        self.ability_details = ability_details or {}

WEAPONS = {
    "Calibrum": MoonstoneWeapon(
        name="Calibrum", moonlight=50,
        passive_effect={"bonus_range": 100},
        on_hit_effect={
            "consumes_mark": True,
            "mark_consume_bonus_damage_flat": 15,
            "mark_consume_bonus_damage_bonus_ad_ratio": 0.20,
            "mark_special_range": 1800
        },
        ability_details={
            "name": "Moonshot", "cost": 10, "base_damage_lvl18": 160,
            "bonus_ad_ratio": 0.60, "ap_ratio": 1.0, "applies_mark": True, "mark_duration": 4.5
        }
    ),
    "Severum": MoonstoneWeapon(
        name="Severum", moonlight=50,
        passive_effect={
            "heal_from_damage_ratio_lvl18": 0.071,
            "ability_heal_from_damage_ratio_lvl18": 0.1775,
            "uncancellable_windup": True
        },
        ability_details={
            "name": "Onslaught", "cost": 10, "duration": 1.75, "bonus_ms_flat": 0.20,
            "num_attacks_base": 6, "num_attacks_bonus_as_ratio": 2,
            "attack_base_damage_lvl18": 40, "attack_bonus_ad_ratio": 0.40,
            "on_hit_effectiveness": 0.25 # Crucial for item interactions
        }
    ),
    "Gravitum": MoonstoneWeapon(
        name="Gravitum", moonlight=50,
        on_hit_effect={"slow_amount": 0.30, "slow_duration": 2.5},
        ability_details={
            "name": "Binding Eclipse", "cost": 10, "base_damage_lvl18": 140,
            "bonus_ad_ratio": 0.50, "ap_ratio": 0.7, "root_duration": 1.0, "damage_type": "magic"
        }
    ),
    "Infernum": MoonstoneWeapon(
        name="Infernum", moonlight=50,
        passive_effect={"primary_target_damage_mod": 1.1},
        on_hit_effect={
            "cone_secondary_target_damage_ratio_lvl18": 1.0,
            "cone_secondary_target_minion_damage_ratio_lvl18": 0.30
        },
        ability_details={
            "name": "Duskwave", "cost": 10, "base_damage_lvl18": 65,
            "bonus_ad_ratio": 0.80, "ap_ratio": 0.7, "triggers_off_hand_attacks": True
        }
    ),
    "Crescendum": MoonstoneWeapon(
        name="Crescendum", moonlight=50,
        passive_effect={
            "max_chakrams": 20, "chakram_duration": 5,
            # CORRECTED: Based on research "0% – 138.5% ... AD bonus physical damage"
            # This is a linear scaling from 0 stacks to 20 stacks. 1.385 / 20 = 0.06925
            "bonus_damage_per_chakram_stack_ratio": 0.06925
        },
        ability_details={
            "name": "Sentry", "cost": 10, "generates_spectral_chakram_on_cast": True
        }
    )
}

# ============================================================
# Item Definitions and Constraints
# ============================================================
ITEMS = {
    # ... (Item dictionary remains the same as provided)
    "Muramana": {"AD": 49.29, "Ability Haste": 31.0, "Mana": 860.0, "name": "Muramana"}, "Axiom Arc": {"AD": 55.0, "Ability Haste": 20.0, "Lethality": 18.0, "UltimateRefund": 0.15, "name": "Axiom Arc"}, "Black Cleaver": {"AD": 40.0, "Ability Haste": 20.0, "Health": 400.0, "ArmorPen": 0.30, "name": "Black Cleaver"}, "Blade of the Ruined King": {"AD": 40.0, "Attack Speed": 0.25, "Lifesteal": 0.10, "OnHitCurrentHealth": 0.05, "name": "Blade of the Ruined King"}, "Bloodthirster": {"AD": 80.0, "Lifesteal": 0.15, "Shield": (165.0, 315.0), "name": "Bloodthirster"}, "Death's Dance": {"AD": 60.0, "Ability Haste": 15.0, "Armor": 50.0, "DamageReduction": 0.30, "name": "Death's Dance"}, "Eclipse": {"AD": 60.0, "Ability Haste": 15.0, "MaxHealthDamage": 0.06, "Shield": (160.0, 80.0), "name": "Eclipse"}, "Essence Reaver": {"AD": 60.0, "Ability Haste": 15.0, "Crit Chance": 0.25, "ManaRestore": 15.0, "name": "Essence Reaver"}, "Guinsoo's Rageblade": {"AD": 30.0, "Ability Power": 30.0, "Attack Speed": 0.25, "OnHitMagicDamage": 30.0, "name": "Guinsoo's Rageblade"}, "Hubris": {"AD": 60.0, "Ability Haste": 10.0, "Lethality": 18.0, "BonusADPerStack": 15.0, "name": "Hubris"}, "Hullbreaker": {"AD": 40.0, "Health": 500.0, "MoveSpeed": 0.04, "BonusArmorMR": (70.0, 130.0), "name": "Hullbreaker"}, "Immortal Shieldbow": {"AD": 55.0, "Crit Chance": 0.25, "Shield": (400.0, 700.0), "Lifesteal": 0.07, "name": "Immortal Shieldbow"}, "Infinity Edge": {"AD": 70.0, "Crit Chance": 0.25, "CritDamage": 0.40, "name": "Infinity Edge"}, "Kraken Slayer": {"AD": 45.0, "Attack Speed": 0.40, "MoveSpeed": 0.04, "BonusPhysicalDamage": (150.0, 200.0), "name": "Kraken Slayer"}, "Lord Dominik's Regards": {"AD": 35.0, "ArmorPen": 0.40, "Crit Chance": 0.25, "name": "Lord Dominik's Regards"}, "Maw of Malmortius": {"AD": 60.0, "Ability Haste": 15.0, "MR": 40.0, "Shield": (200.0, 150.0), "Omnivamp": 0.10, "name": "Maw of Malmortius"}, "Mercurial Scimitar": {"AD": 40.0, "MR": 40.0, "Lifesteal": 0.10, "name": "Mercurial Scimitar"}, "Mortal Reminder": {"AD": 35.0, "Armor Pen": 0.35, "Crit Chance": 0.25, "GrievousWounds": True, "name": "Mortal Reminder"}, "Nashor's Tooth": {"Ability Power": 80.0, "Ability Haste": 15.0, "Attack Speed": 0.50, "OnHitMagicDamage": 15.0, "name": "Nashor's Tooth"}, "Navori Flickerblade": {"Attack Speed": 0.40, "Crit Chance": 0.25, "MoveSpeed": 0.04, "CooldownReduction": 0.15, "name": "Navori Flickerblade"}, "Opportunity": {"AD": 55.0, "Lethality": 15.0, "MoveSpeedOutOfCombat": (11.0, 7.0), "name": "Opportunity"}, "Phantom Dancer": {"Attack Speed": 0.60, "Crit Chance": 0.25, "MoveSpeed": 0.08, "name": "Phantom Dancer"}, "Rapid Firecannon": {"Attack Speed": 0.35, "Crit Chance": 0.25, "MoveSpeed": 0.04, "name": "Rapid Firecannon"}, "Ravenous Hydra": {"AD": 65.0, "Ability Haste": 15.0, "Lifesteal": 0.12, "Cleave": 0.40, "name": "Ravenous Hydra"}, "Runaan's Hurricane": {"Attack Speed": 0.40, "Crit Chance": 0.25, "MoveSpeed": 0.04, "name": "Runaan's Hurricane"}, "Serpent's Fang": {"AD": 55.0, "Lethality": 15.0, "ShieldReduction": 0.50, "name": "Serpent's Fang"}, "Serylda's Grudge": {"AD": 45.0, "Ability Haste": 20.0, "ArmorPen": 0.30, "Slow": 0.30, "name": "Serylda's Grudge"}, "Statikk Shiv": {"AD": 45.0, "Attack Speed": 0.30, "MoveSpeed": 0.04, "MagicDamage": 60.0, "name": "Statikk Shiv"}, "Sterak's Gage": {"Health": 400.0, "Tenacity": 0.20, "BonusAD": 0.45, "name": "Sterak's Gage"}, "Terminus": {"AD": 30.0, "Attack Speed": 0.35, "OnHitMagicDamage": 30.0, "ArmorMRPerStack": (6.0, 7.0, 8.0), "ArmorPenMagicPenPerStack": 0.10, "name": "Terminus"}, "The Collector": {"AD": 50.0, "Lethality": 10.0, "Crit Chance": 0.25, "Execute": 0.05, "name": "The Collector"}, "Trinity Force": {"AD": 36.0, "Ability Haste": 15.0, "Attack Speed": 0.30, "Health": 333.0, "SpellbladeDamage": 2.0, "name": "Trinity Force"}, "Voltaic Cyclosword": {"AD": 55.0, "Ability Haste": 10.0, "Lethality": 18.0, "Slow": 0.99, "BonusPhysicalDamage": 100.0, "name": "Voltaic Cyclosword"}, "Wit's End": {"MR": 45.0, "Attack Speed": 0.50, "Tenacity": 0.20, "OnHitMagicDamage": 45.0, "name": "Wit's End"}, "Youmuu's Ghostblade": {"AD": 55.0, "Lethality": 18.0, "MoveSpeedOutOfCombat": (20.0, 10.0), "name": "Youmuu's Ghostblade"}, "Sundered sky":{"AD":40,"Ability Haste":10,"Health":400,"CritDamage": 0.75, "HealMissingHealth":0.06, "name":"Sundered sky"}
}
ITEM_CONSTRAINTS = {"last_whisper": {"items": ["Lord Dominik's Regards", "Serylda's Grudge", "Mortal Reminder", "Black Cleaver"], "max": 1}, "lifeline": {"items": ["Immortal Shieldbow", "Maw of Malmortius", "Sterak's Gage"], "max": 1}}
def is_valid_build(combo):
    for constraint_group in ITEM_CONSTRAINTS.values():
        if sum(1 for item in combo if item in constraint_group["items"]) > constraint_group["max"]:
            return False
    return True

# ============================================================
# Helper Functions
# ============================================================
def apply_physical_mitigation(damage, enemy_armor, armor_pen_percent=0.0, lethality=0.0):
    # CORRECTED: Lethality is flat armor penetration as of V14.1 patch research.
    # The old level-scaling formula is removed.
    armor_after_percent_pen = enemy_armor * (1.0 - armor_pen_percent)
    final_armor = armor_after_percent_pen - lethality

    if final_armor >= 0:
        multiplier = 100.0 / (100.0 + final_armor)
    else:
        multiplier = 2.0 - (100.0 / (100.0 - final_armor))
    return damage * multiplier

def apply_magic_mitigation(damage, enemy_mr):
    if enemy_mr >= 0:
        return damage * (100 / (100 + enemy_mr))
    else:
        return damage * (2 - (100 / (100 - enemy_mr)))

def chunkify(iterable, chunk_size):
    for i in range(0, len(iterable), chunk_size):
        yield iterable[i:i + chunk_size]

# ============================================================
# Aphelios Simulator Class
# ============================================================
class ApheliosSimulator:
    def __init__(self, items, enemy_armor=250.0, enemy_health=3500.0, enemy_mr=50.0):
        self.item_names = items
        self.item_stats = [ITEMS[item] for item in items if item in ITEMS]
        self.stats = self._calculate_initial_stats()

        self.enemy_armor = float(enemy_armor)
        self.enemy_health = float(enemy_health)
        self.enemy_mr = float(enemy_mr)
        
        # Simulation State
        self.weapon_queue = deque(["Calibrum", "Severum", "Gravitum", "Infernum", "Crescendum"])
        self.main_hand_name = self.weapon_queue[0]
        self.off_hand_name = self.weapon_queue[1]
        self.weapon_ammo = {w: 50 for w in WEAPONS}
        
        self.time = 0.0
        self.ability_cooldown_timestamp = 0.0
        self.chakram_stacks = 0
        self.active_marks = {}
        self.attack_counter = 0 # For stateful item procs like Kraken Slayer
        self.spellblade_ready = False # For stateful item procs like Trinity Force

    @functools.lru_cache(maxsize=1) # Cache only the final computed stats for one build
    def _calculate_initial_stats(self):
        stats = {
            "BonusAD": INNATE_BONUS_AD,
            "BonusAS_percent": INNATE_BONUS_AS_PERCENT,
            "Crit": 0.0, "CritDmg": DEFAULT_CRIT_DAMAGE,
            "Lethality": INNATE_LETHALITY,
            "ArmorPen_percent": 0.0,
            "LS": 0.0, "Omnivamp": 0.0,
            "AttackRange": BASE_ATTACK_RANGE,
            "Health": BASE_HEALTH, "Armor": BASE_ARMOR, "MR": BASE_MR, "Mana": BASE_MANA,
        }

        has_infinity_edge = "Infinity Edge" in self.item_names
        
        for item in self.item_stats:
            stats["BonusAD"] += item.get("AD", 0.0)
            stats["BonusAS_percent"] += item.get("Attack Speed", 0.0) * 100
            stats["Crit"] += item.get("Crit Chance", 0.0)
            stats["Lethality"] += item.get("Lethality", 0.0)
            stats["LS"] += item.get("Lifesteal", 0.0)
            stats["Omnivamp"] += item.get("Omnivamp", 0.0)
            stats["ArmorPen_percent"] = max(stats["ArmorPen_percent"], item.get("ArmorPen", 0.0), item.get("Armor Pen", 0.0))
            if "CritDamage" in item:
                stats["CritDmg"] += item["CritDamage"]
        
        # Final calculations
        stats["TotalAD"] = BASE_AD_LEVEL18 + stats["BonusAD"]
        stats["TotalAS"] = BASE_AS * (1 + (stats["BonusAS_percent"] / 100) * AS_RATIO)
        stats["TotalAS"] = min(2.5, stats["TotalAS"]) # AS is capped at 2.5
        stats["Crit"] = min(1.0, stats["Crit"])
        if has_infinity_edge: stats["CritDmg"] += 0.4
            
        return stats

    def rotate_weapon(self):
        self.time += WEAPON_SWAP_TIME
        exhausted_name = self.weapon_queue.popleft()
        self.weapon_queue.append(exhausted_name)
        self.weapon_ammo[exhausted_name] = WEAPONS[exhausted_name].moonlight
        self.main_hand_name = self.weapon_queue[0]
        self.off_hand_name = self.weapon_queue[1]

    def calculate_dps(self, duration=60):
        total_damage = 0.0
        while self.time < duration:
            # Check for weapon rotation
            if self.weapon_ammo[self.main_hand_name] <= 0:
                self.rotate_weapon()
                if self.time >= duration: break
            
            main_weapon = WEAPONS[self.main_hand_name]
            
            # Simple AI: Use ability if off cooldown
            if self.time >= self.ability_cooldown_timestamp and self.weapon_ammo[self.main_hand_name] >= main_weapon.ability_details.get("cost", 10):
                total_damage += self.simulate_ability()
                self.time += ABILITY_CAST_TIME
                self.ability_cooldown_timestamp = self.time + ABILITY_COOLDOWN
                self.spellblade_ready = True # An ability was used, ready Spellblade
            else:
                # Basic attack
                total_damage += self.simulate_attack()
                self.time += 1.0 / self.stats["TotalAS"]
        
        return total_damage / duration if duration > 0 else 0

    def simulate_attack(self):
        main_weapon = WEAPONS[self.main_hand_name]
        self.weapon_ammo[self.main_hand_name] -= 1
        self.attack_counter += 1

        physical_damage, magic_damage, true_damage = 0.0, 0.0, 0.0

        # --- Base Attack Damage ---
        base_attack_damage = self.stats["TotalAD"]
        if main_weapon.name == "Infernum":
            base_attack_damage *= main_weapon.passive_effect.get("primary_target_damage_mod", 1.0)
        
        # --- Crescendum Bonus Damage ---
        if main_weapon.name == "Crescendum":
            bonus_damage_ratio = main_weapon.passive_effect.get("bonus_damage_per_chakram_stack_ratio", 0)
            base_attack_damage += (self.chakram_stacks * bonus_damage_ratio) * self.stats["BonusAD"]

        # --- Critical Strike ---
        is_crit = random.random() < self.stats["Crit"]
        if is_crit:
            base_attack_damage *= self.stats["CritDmg"]
        
        physical_damage += base_attack_damage

        # --- Item On-Hit Effects (Stateful) ---
        if self.spellblade_ready and "Trinity Force" in self.item_names:
            physical_damage += 2.0 * BASE_AD_LEVEL18
            self.spellblade_ready = False
        if self.attack_counter % 3 == 0 and "Kraken Slayer" in self.item_names:
            true_damage += ITEMS["Kraken Slayer"]["BonusPhysicalDamage"][0]
        
        # --- Infernum Cone Damage (Single Target DPS assumes 1 additional target hit) ---
        if main_weapon.name == "Infernum":
            # Cone damage is based on the triggering attack's damage
            cone_damage = base_attack_damage * main_weapon.on_hit_effect.get("cone_secondary_target_damage_ratio_lvl18", 1.0)
            physical_damage += cone_damage # Adding damage for one secondary target

        # --- Final Mitigation ---
        mitigated_physical = apply_physical_mitigation(physical_damage, self.enemy_armor, self.stats["ArmorPen_percent"], self.stats["Lethality"])
        # (Magic/True damage from items would be added here and mitigated if necessary)
        
        return mitigated_physical + magic_damage + true_damage

    def simulate_ability(self):
        main_weapon = WEAPONS[self.main_hand_name]
        off_hand_weapon = WEAPONS[self.off_hand_name]
        ability_details = main_weapon.ability_details
        
        self.weapon_ammo[self.main_hand_name] -= ability_details.get("cost", 10)
        
        physical_damage, magic_damage = 0.0, 0.0
        
        base_dmg = ability_details.get("base_damage_lvl18", 0)
        bonus_ad_ratio = ability_details.get("bonus_ad_ratio", 0.0)
        ap_ratio = ability_details.get("ap_ratio", 0.0)
        
        raw_damage = base_dmg + (self.stats["BonusAD"] * bonus_ad_ratio) # (AP scaling ignored for now)

        # --- Specific Ability and Synergy Logic ---
        if main_weapon.name == "Severum": # Onslaught
            num_attacks = ability_details.get("num_attacks_base", 6)
            num_attacks += int(self.stats["BonusAS_percent"] / 100 * ability_details.get("num_attacks_bonus_as_ratio", 2))
            
            single_hit_damage = ability_details.get("attack_base_damage_lvl18", 0) + self.stats["BonusAD"] * ability_details.get("attack_bonus_ad_ratio", 0)
            raw_damage = 0
            # Simulating Onslaught hits with synergy
            for _ in range(num_attacks):
                raw_damage += single_hit_damage
                # SYNERGY: Severum + Crescendum -> Onslaught generates chakrams
                if off_hand_weapon.name == "Crescendum":
                    self.chakram_stacks = min(20, self.chakram_stacks + 1)
        
        elif main_weapon.name == "Infernum": # Duskwave
            # SYNERGY: Infernum + Crescendum -> Duskwave followers generate chakrams
            if ability_details.get("triggers_off_hand_attacks") and off_hand_weapon.name == "Crescendum":
                # Assuming volley hits 3 times for synergy demonstration
                self.chakram_stacks = min(20, self.chakram_stacks + 3)
            # Duskwave itself deals damage, then off-hand attack follows (simplified here)
            physical_damage += raw_damage

        elif main_weapon.name == "Crescendum": # Sentry
            if ability_details.get("generates_spectral_chakram_on_cast"):
                self.chakram_stacks = min(20, self.chakram_stacks + 1)
            # Sentry damage is a pet and complex, for now we only model the chakram gain.
        
        # Assign damage to correct type
        if ability_details.get("damage_type") == "magic":
            magic_damage += raw_damage
        else:
            physical_damage += raw_damage

        # --- Final Mitigation ---
        mitigated_physical = apply_physical_mitigation(physical_damage, self.enemy_armor, self.stats["ArmorPen_percent"], self.stats["Lethality"])
        mitigated_magic = apply_magic_mitigation(magic_damage, self.enemy_mr)
        
        return mitigated_physical + mitigated_magic

# ============================================================
# Simulation Orchestration
# ============================================================
def simulate_build_chunk(builds_chunk, duration, armor, health, mr):
    results = []
    for combo in builds_chunk:
        simulator = ApheliosSimulator(combo, enemy_armor=armor, enemy_health=health, enemy_mr=mr)
        dps = simulator.calculate_dps(duration)
        results.append((combo, dps))
    return results

def optimize_aphelios_build(simulation_duration=60, enemy_armor=200, enemy_health=3000, enemy_mr=100, chunk_size=500):
    item_keys = list(ITEMS.keys())
    valid_combos = [combo for combo in itertools.combinations(item_keys, 5) if is_valid_build(combo)]
    
    if not valid_combos:
        print("No valid item combinations found.")
        return []

    chunks = list(chunkify(valid_combos, chunk_size))
    all_results = []
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
    print("Starting Aphelios Build Optimization (Enhanced Version)...")
    # Simulation parameters
    duration = 60  # Duration of a typical teamfight
    enemy_armor_val = 150
    enemy_health_val = 2500
    enemy_mr_val = 75
    
    top_builds = optimize_aphelios_build(
        simulation_duration=duration,
        enemy_armor=enemy_armor_val,
        enemy_health=enemy_health_val,
        enemy_mr=enemy_mr_val,
        chunk_size=200
    )

    print("\n--- Top 10 Aphelios Builds ---")
    if top_builds:
        for i, (combo, dps) in enumerate(top_builds[:10]):
            print(f"{i+1}. Build: {', '.join(combo)}")
            print(f"   Simulated DPS: {dps:.2f}")
    else:
        print("No builds were successfully simulated.")