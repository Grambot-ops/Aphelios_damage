import itertools
import random
from collections import deque
import functools
import concurrent.futures
import os

# ============================================================
# Aphelios Simulation Code with Optimized Runtime, Integrated Damage Calculation,
# Weapon Synergies, and Stochastic Critical Strike Simulation
#
# Research on Aphelios (based on League of Legends Wiki):
#   - Base AD: 94.1, Base AS: 0.64, Health: 2334, Mana: 1062, Armor: 97.4, MR: 52.1,
#     Crit Damage: 175% (1.75), Move Speed: 325, Attack Range: 550.
#
# Damage research shows that physical damage is mitigated by:
#    effective_damage = raw_damage * (100 / (100 + armor))   if armor >= 0
#    effective_damage = raw_damage * (2 - 100 / (100 - armor)) if armor < 0
#
# Weapon synergy multipliers are applied based on official mechanics.
#
# For improved realism—and to reflect that critical strikes have a stronger impact—
# the simulation now determines crits stochastically rather than using an averaged
# expected value. Additionally, runtime is optimized using ProcessPoolExecutor with
# chunking.
# ============================================================

# Base champion stats from research
BASE_AD_LEVEL18 = 94.1
BASE_AS = 0.64  # Corrected from 0.658; 0.658 is the AS Ratio
DEFAULT_CRIT_DAMAGE = 1.75  # 175% crit damage
BASE_HEALTH = 2334
BASE_MANA = 1062
BASE_ARMOR = 97.4
BASE_MR = 52.1
BASE_MOVE_SPEED = 325
BASE_ATTACK_RANGE = 550

# Simulation constants
ABILITY_CAST_TIME = 0.5
ABILITY_COOLDOWN = 3.0
ROTATION_DELAY = 0.3

# ============================================================
# Weapon Synergy Multipliers (based on official mechanics)
# ============================================================

WEAPON_SYNERGIES = {
    ("Calibrum", "Severum"): {
        "description": "Long-range sustain",
        "multiplier": 1.15,
        "conditions": {
            "range_threshold": 650,
            "heal_amplifier": 1.2
        }
    },
    ("Calibrum", "Gravitum"): {
        "description": "Control combo",
        "multiplier": 1.2,
        "conditions": {
            "mark_duration": 4.5,
            "root_duration": 1.35
        }
    },
    ("Calibrum", "Infernum"): {
        "description": "AOE marking",
        "multiplier": 1.25,
        "conditions": {
            "splash_radius": 400,
            "mark_splash": True
        }
    },
    ("Calibrum", "Crescendum"): {
        "description": "Turret sniper",
        "multiplier": 1.3,
        "conditions": {
            "turret_range": 1800,
            "mark_generation": 2
        }
    },
    ("Severum", "Gravitum"): {
        "description": "Drain tank",
        "multiplier": 1.2,
        "conditions": {
            "heal_amplifier": 1.15,
            "slow_amplifier": 1.2
        }
    },
    ("Severum", "Infernum"): {
        "description": "AOE lifesteal",
        "multiplier": 1.3,
        "conditions": {
            "splash_healing": True,
            "heal_reduction": 0.6
        }
    },
    ("Severum", "Crescendum"): {
        "description": "Chakram stacking",
        "multiplier": 1.35,
        "conditions": {
            "chakram_generation": 2,
            "heal_per_chakram": 0.02
        }
    },
    ("Gravitum", "Infernum"): {
        "description": "AOE control",
        "multiplier": 1.25,
        "conditions": {
            "slow_splash": True,
            "root_splash": True
        }
    },
    ("Gravitum", "Crescendum"): {
        "description": "Turret control",
        "multiplier": 1.2,
        "conditions": {
            "turret_slow": True,
            "slow_chakram_gen": 1
        }
    },
    ("Infernum", "Crescendum"): {
        "description": "AOE chakrams",
        "multiplier": 1.4,
        "conditions": {
            "splash_chakram_gen": True,
            "chakram_splash": True
        }
    }
}

# Weapon Definitions
class MoonstoneWeapon:
    """
    Represents a Moonstone weapon for Aphelios.
    Each weapon has a unique set of attributes based on research.txt.
    """
    def __init__(self, name, moonlight, passive_effect=None, on_hit_effect=None, ability_details=None):
        self.name = name
        self.moonlight = moonlight
        self.passive_effect = passive_effect if passive_effect else {}
        self.on_hit_effect = on_hit_effect if on_hit_effect else {}
        self.ability_details = ability_details if ability_details else {}

WEAPONS = {
    "Calibrum": MoonstoneWeapon(
        name="Calibrum",
        moonlight=50,
        passive_effect={
            "bonus_range": 100,
        },
        # Mark application is via ability. Mark consumption is on next auto vs marked target.
        on_hit_effect={ # This applies to the empowered attack on a marked target
            "consumes_mark": True, # Special condition for this attack type
            "mark_consume_bonus_damage_flat": 15,
            "mark_consume_bonus_damage_bonus_ad_ratio": 0.20,
            "mark_special_range": 1800 # Range of the mark-consuming attack
        },
        ability_details={ # Moonshot
            "name": "Moonshot",
            "cost": 10, # Standard Q cost (10 ammo)
            "base_damage_lvl18": 160,
            "bonus_ad_ratio": 0.60, # research: 42-60%
            "ap_ratio": 1.0,
            "applies_mark": True,
            "mark_duration": 4.5
        }
    ),
    "Severum": MoonstoneWeapon(
        name="Severum",
        moonlight=50,
        passive_effect={ # Innate healing from Severum's attacks (including Onslaught)
            "heal_from_damage_ratio_lvl18": 0.071, # research: 2-7.1% for basic attacks
            "ability_heal_from_damage_ratio_lvl18": 0.1775, # research: 5-17.75% for abilities (Onslaught hits)
            "shield_conversion_from_excess_heal_max_hp_ratio": 0.06,
            "shield_conversion_base_lvl18": 140 # research: 10-140
        },
        on_hit_effect={}, # Basic attacks primarily heal via passive_effect
        ability_details={ # Onslaught
            "name": "Onslaught",
            "cost": 10,
            "duration": 1.75,
            "bonus_ms_flat": 0.20,
            "bonus_ms_ap_ratio": 0.10, # per 100 AP
            "num_attacks_base": 6,
            "num_attacks_bonus_as_ratio": 2, # per 100% bonus AS
            "attack_base_damage_lvl18": 40, # research: 10-40
            "attack_bonus_ad_ratio": 0.40, # research: 22-40%
            "on_hit_effectiveness": 0.25 # For item on-hits during Onslaught
        }
    ),
    "Gravitum": MoonstoneWeapon(
        name="Gravitum",
        moonlight=50,
        passive_effect={},
        on_hit_effect={ # Applied by basic attacks
            "slow_amount": 0.30,
            "slow_duration": 2.5,
            "slow_decay_to": 0.10,
            "slow_decay_after": 0.7
        },
        ability_details={ # Binding Eclipse
            "name": "Binding Eclipse",
            "cost": 10,
            "base_damage_lvl18": 140, # research: 50-140
            "bonus_ad_ratio": 0.50, # research: 32-50%
            "ap_ratio": 0.7,
            "root_duration": 1.0,
            "damage_type": "magic", # Important: Gravitum Q deals magic damage
            "consumes_gravitum_mark_for_root": True # Consumes slow marks to root
        }
    ),
    "Infernum": MoonstoneWeapon(
        name="Infernum",
        moonlight=50,
        passive_effect={ # Basic attacks with Infernum
            "primary_target_damage_mod": 1.1, # 110% AD to primary target
        },
        on_hit_effect={ # Cone damage from basic attacks
             # research: "splits into a cone of 4 lesser bolts... Secondary targets hit by any bolt are dealt 75/100% (based on level) of the triggering attack's damage"
            "cone_num_bolts": 4, # For non-crit
            "cone_crit_num_bolts": 6, # For crit
            "cone_crit_wider_mod": 1.5, # 50% wider cone on crit
            "cone_secondary_target_damage_ratio_lvl18": 1.0, # 100% of triggering attack's damage at lvl 18
            "cone_secondary_target_minion_damage_ratio_lvl18": 0.30 # research: 23/30%
        },
        ability_details={ # Duskwave
            "name": "Duskwave",
            "cost": 10,
            "base_damage_lvl18": 65, # research: 25-65
            "bonus_ad_ratio": 0.80, # research: 56-80%
            "ap_ratio": 0.7,
            "triggers_off_hand_attacks": True # Locks on, then fires volley from off-hand
        }
    ),
    "Crescendum": MoonstoneWeapon(
        name="Crescendum",
        moonlight=50,
        passive_effect={
            "max_chakrams": 20,
            "chakram_duration": 5,
            # Basic attack damage scaling per chakram needs to be handled in simulation logic
            # research: "Each chakram increases the damage of Crescendum's basic attack."
            # Placeholder: 0.02 AD per stack from old code, will use if no better value found.
            "bonus_ad_per_chakram_stack": 0.02 # Placeholder, needs verification
        },
        on_hit_effect={ # When main Crescendum basic attack hits and returns
            "generates_chakram_on_return": True,
        },
        ability_details={ # Sentry (placeholder, research.txt snippet is incomplete for Sentry)
            "name": "Sentry",
            "cost": 10,
            "generates_spectral_chakram_on_cast": True, # Abilities cast with Crescendum generate a temporary chakram
            "sentry_attacks_with_off_hand": True
            # Sentry duration, attack speed, etc., would be needed for full simulation
        }
    )
}

# ============================================================#
# Item Definitions              
# ============================================================
ITEMS = {
    "Muramana": {"AD": 49.29, "Ability Haste": 31.0, "Mana": 860.0, "name": "Muramana"},
    "Axiom Arc": {"AD": 55.0, "Ability Haste": 20.0, "Lethality": 18.0, "UltimateRefund": 0.15, "name": "Axiom Arc"},
    "Black Cleaver": {"AD": 40.0, "Ability Haste": 20.0, "Health": 400.0, "ArmorPen": 0.30, "name": "Black Cleaver"},
    "Blade of the Ruined King": {"AD": 40.0, "Attack Speed": 0.25, "Lifesteal": 0.10, "OnHitCurrentHealth": 0.05, "name": "Blade of the Ruined King"}, # bork is 5% currentHP for ranged champs - ueberheblichkeit
    "Bloodthirster": {"AD": 80.0, "Lifesteal": 0.15, "Shield": (165.0, 315.0), "name": "Bloodthirster"},
    "Death's Dance": {"AD": 60.0, "Ability Haste": 15.0, "Armor": 50.0, "DamageReduction": 0.30, "name": "Death's Dance"},
    "Eclipse": {"AD": 60.0, "Ability Haste": 15.0, "MaxHealthDamage": 0.06, "Shield": (160.0, 80.0), "name": "Eclipse"},
    "Essence Reaver": {"AD": 60.0, "Ability Haste": 15.0, "Crit Chance": 0.25, "ManaRestore": 15.0, "name": "Essence Reaver"},
    "Guinsoo's Rageblade": {"AD": 30.0, "Ability Power": 30.0, "Attack Speed": 0.25, "OnHitMagicDamage": 30.0, "name": "Guinsoo's Rageblade"},
    "Hubris": {"AD": 60.0, "Ability Haste": 10.0, "Lethality": 18.0, "BonusADPerStack": 15.0, "name": "Hubris"},
    "Hullbreaker": {"AD": 40.0, "Health": 500.0, "MoveSpeed": 0.04, "BonusArmorMR": (70.0, 130.0), "name": "Hullbreaker"},
    "Immortal Shieldbow": {"AD": 55.0, "Crit Chance": 0.25, "Shield": (400.0, 700.0), "Lifesteal": 0.07, "name": "Immortal Shieldbow"},
    "Infinity Edge": {"AD": 70.0, "Crit Chance": 0.25, "CritDamage": 0.40, "name": "Infinity Edge"},
    "Kraken Slayer": {"AD": 45.0, "Attack Speed": 0.40, "MoveSpeed": 0.04, "BonusPhysicalDamage": (150.0, 200.0), "name": "Kraken Slayer"},
    "Lord Dominik's Regards": {"AD": 35.0, "ArmorPen": 0.40, "Crit Chance": 0.25, "name": "Lord Dominik's Regards"},
    "Maw of Malmortius": {"AD": 60.0, "Ability Haste": 15.0, "MR": 40.0, "Shield": (200.0, 150.0), "Omnivamp": 0.10, "name": "Maw of Malmortius"},
    "Mercurial Scimitar": {"AD": 40.0, "MR": 40.0, "Lifesteal": 0.10, "name": "Mercurial Scimitar"},
    "Mortal Reminder": {"AD": 35.0, "Armor Pen": 0.35, "Crit Chance": 0.25, "GrievousWounds": True, "name": "Mortal Reminder"},
    "Nashor's Tooth": {"Ability Power": 80.0, "Ability Haste": 15.0, "Attack Speed": 0.50, "OnHitMagicDamage": 15.0, "name": "Nashor's Tooth"},
    "Navori Flickerblade": {"Attack Speed": 0.40, "Crit Chance": 0.25, "MoveSpeed": 0.04, "CooldownReduction": 0.15, "name": "Navori Flickerblade"},
    "Opportunity": {"AD": 55.0, "Lethality": 15.0, "MoveSpeedOutOfCombat": (11.0, 7.0), "name": "Opportunity"},
    "Phantom Dancer": {"Attack Speed": 0.60, "Crit Chance": 0.25, "MoveSpeed": 0.08, "name": "Phantom Dancer"},
    "Rapid Firecannon": {"Attack Speed": 0.35, "Crit Chance": 0.25, "MoveSpeed": 0.04, "name": "Rapid Firecannon"},
    "Ravenous Hydra": {"AD": 65.0, "Ability Haste": 15.0, "Lifesteal": 0.12, "Cleave": 0.40, "name": "Ravenous Hydra"},
    "Runaan's Hurricane": {"Attack Speed": 0.40, "Crit Chance": 0.25, "MoveSpeed": 0.04, "name": "Runaan's Hurricane"},
    "Serpent's Fang": {"AD": 55.0, "Lethality": 15.0, "ShieldReduction": 0.50, "name": "Serpent's Fang"},
    "Serylda's Grudge": {"AD": 45.0, "Ability Haste": 20.0, "ArmorPen": 0.30, "Slow": 0.30, "name": "Serylda's Grudge"},
    "Statikk Shiv": {"AD": 45.0, "Attack Speed": 0.30, "MoveSpeed": 0.04, "MagicDamage": 60.0, "name": "Statikk Shiv"},
    "Sterak's Gage": {"Health": 400.0, "Tenacity": 0.20, "BonusAD": 0.45, "name": "Sterak's Gage"},
    "Terminus": {"AD": 30.0, "Attack Speed": 0.35, "OnHitMagicDamage": 30.0, "ArmorMRPerStack": (6.0, 7.0, 8.0), "ArmorPenMagicPenPerStack": 0.10, "name": "Terminus"},
    "The Collector": {"AD": 50.0, "Lethality": 10.0, "Crit Chance": 0.25, "Execute": 0.05, "name": "The Collector"},
    "Trinity Force": {"AD": 36.0, "Ability Haste": 15.0, "Attack Speed": 0.30, "Health": 333.0, "SpellbladeDamage": 2.0, "name": "Trinity Force"},
    "Voltaic Cyclosword": {"AD": 55.0, "Ability Haste": 10.0, "Lethality": 18.0, "Slow": 0.99, "BonusPhysicalDamage": 100.0, "name": "Voltaic Cyclosword"},
    "Wit's End": {"MR": 45.0, "Attack Speed": 0.50, "Tenacity": 0.20, "OnHitMagicDamage": 45.0, "name": "Wit's End"},
    "Youmuu's Ghostblade": {"AD": 55.0, "Lethality": 18.0, "MoveSpeedOutOfCombat": (20.0, 10.0), "name": "Youmuu's Ghostblade"},
    "Sundered sky":{"AD":40,"Ability Haste":10,"Health":400,"CritDamage": 0.75, "HealMissingHealth":0.06, "name":"Sundered sky"}
}

ITEM_CONSTRAINTS = {
    "last_whisper": {
        "items": ["Lord Dominik's Regards", "Serylda's Grudge", "Mortal Reminder","Black Cleaver"],
        "max": 1
    },
    "lifeline": {
        "items": ["Immortal Shieldbow", "Maw of Malmortius", "Sterak's Gage"],
        "max": 1
    }
}

def is_valid_build(combo):
    """
    Checks if a build is valid according to item constraints.
    Returns True if valid, False if invalid.
    """
    for constraint_group in ITEM_CONSTRAINTS.values():
        count = sum(1 for item in combo if item in constraint_group["items"])
        if count > constraint_group["max"]:
            return False
    return True

# ============================================================
# Weapon Damage Factors (synergy factors)
# ============================================================
WEAPON_DAMAGE_FACTORS = {
    "Calibrum": {"AD": 3.0, "Lethality": 2.5, "Crit Chance": 2.0, "Bonus Range": 1.5},
    "Severum": {"Attack Speed": 3.0, "AD": 2.0, "Lifesteal": 2.5, "Omnivamp": 1.5},
    "Gravitum": {"Armor Pen": 3.0, "AD": 2.0, "Slow": 2.0},
    "Infernum": {"Attack Speed": 3.0, "AD": 2.5, "Crit Chance": 2.0, "Magic Damage": 1.5},
    "Crescendum": {"Attack Speed": 4.0, "OnHit": 3.0, "AD": 2.0, "Armor": 1.0, "MR": 1.0}
}

# ============================================================
# Helper Function: Apply Physical Damage Mitigation
#
# Based on research:
#    effective_damage = raw_damage * (100 / (100 + armor))   if armor >= 0
#    effective_damage = raw_damage * (2 - 100 / (100 - armor)) if armor < 0
# ============================================================

def apply_physical_mitigation(damage, enemy_armor, armor_pen=0.0, lethality=0.0, attacker_level=18):
    # Calculate lethality_value based on attacker_level
    # Standard formula for lethality: Flat Armor Reduction = Lethality * (0.6 + 0.4 * AttackerLevel / 18)
    lethality_value = lethality * (0.6 + (0.4 * attacker_level / 18.0))

    # Calculate final_armor after percentage penetration and lethality
    armor_after_pen = enemy_armor * (1.0 - armor_pen)
    final_armor = armor_after_pen - lethality_value # Allow final_armor to be negative

    # Damage calculation based on final_armor
    if final_armor >= 0:
        multiplier = 100.0 / (100.0 + final_armor)
    else:
        # Formula for negative armor: 2 - 100 / (100 - armor)
        # Note: final_armor here is negative, so (100.0 - final_armor) becomes (100.0 + abs(final_armor))
        multiplier = 2.0 - (100.0 / (100.0 - final_armor))
    return damage * multiplier

# ============================================================
# Helper Function: Chunkify
# ============================================================#
def chunkify(iterable, chunk_size):
    """Yield successive n-sized chunks from iterable."""
    for i in range(0, len(iterable), chunk_size):
        yield iterable[i:i + chunk_size]

# ============================================================
# Aphelios Simulator
# ============================================================
class ApheliosSimulator:
    """Simulates Aphelios' damage output and build performance."""
    def __init__(self, items, enemy_armor=250.0, enemy_health=3500.0, enemy_mr=50.0, weapon_switch_delay=ROTATION_DELAY, simulate_random=True): # Added enemy_mr parameter and default
        self.weapon_queue = deque(["Calibrum", "Severum", "Gravitum", "Infernum", "Crescendum"])
        self.main_hand_name = self.weapon_queue[0]
        self.off_hand_name = self.weapon_queue[1]
        self.main_hand = WEAPONS[self.main_hand_name]
        self.off_hand = WEAPONS[self.off_hand_name]
        self.item_names = items
        # Assuming ITEMS is a globally defined dictionary
        self.item_stats = [ITEMS[item] for item in items if item in ITEMS]
        self.stats = self._calculate_base_stats(tuple(items)) # Pass items_tuple
        self.enemy_armor = float(enemy_armor)
        self.enemy_health = float(enemy_health)
        self.enemy_mr = float(enemy_mr) # Store enemy_mr
        self.time = 0.0  # Simulation time in seconds
        self.ability_cooldown = 0.0
        self.weapon_ammo = {w_name: WEAPONS[w_name].moonlight for w_name in WEAPONS} # Initialize with correct moonlight
        self.chakram_stacks = 0
        self.active_chakrams = set() # Stores timestamps of when chakrams expire
        self.crescendum_return_times = {} # Tracks return times for Crescendum basic attacks
        self.active_marks = {} # weapon_name: expiry_time
        # Ensure all weapon ammo is initialized correctly based on their definition
        for weapon_name, weapon_obj in WEAPONS.items():
            if weapon_name not in self.weapon_ammo:
                 self.weapon_ammo[weapon_name] = weapon_obj.moonlight

    def use_ammo(self, amount: int):
        """Consumes ammo for the main-hand weapon and rotates if empty."""
        if self.main_hand_name not in self.weapon_ammo:
            # This case should ideally not happen if initialized correctly
            self.weapon_ammo[self.main_hand_name] = WEAPONS[self.main_hand_name].moonlight

        self.weapon_ammo[self.main_hand_name] -= amount
        if self.weapon_ammo[self.main_hand_name] <= 0:
            self.rotate_weapon()

    @functools.lru_cache(maxsize=128)
    def _calculate_base_stats(self, items_tuple):
        items = list(items_tuple)
        stats = {
            "AD": BASE_AD_LEVEL18,
            "AS": 0.658,
            "Crit": 0.0,
            "CritDmg": DEFAULT_CRIT_DAMAGE,
            "Lethality": 0.0,
            "ArmorPen": 0.0,
            "MagicPen": 0.0,
            "OnHit": 0.0, # Placeholder for generic on-hit, specific items need handling
            "LS": 0.0,
            "Omnivamp": 0.0,
            "BonusAD": 0.0,
            "AbilityHaste": 0.0,
            "AttackRange": BASE_ATTACK_RANGE, # Start with base attack range
            "Health": BASE_HEALTH,
            "Armor": BASE_ARMOR,
            "MR": BASE_MR,
            "Mana": BASE_MANA,
            "MoveSpeed": BASE_MOVE_SPEED,
        }

        has_infinity_edge = False
        bonus_ad = 0.0
        
        for item in self.item_stats:
            for stat, value in item.items():
                if stat == "CritDamage":
                    stats["CritDmg"] += float(value)  # Handle crit damage items
                elif stat == "name":
                    if value == "Infinity Edge":
                        has_infinity_edge = True
                    continue
                elif stat == "Crit Chance":
                    stats["Crit"] += float(value)
                    continue
                elif stat == "AD":
                    bonus_ad += float(value)
                    continue
                elif stat in ["ArmorPen", "Armor Pen"]:
                    stats["ArmorPen"] = max(stats["ArmorPen"], float(value))
                elif stat == "Lethality":
                    stats["Lethality"] += float(value)
                    continue
                else:
                    if isinstance(value, tuple):
                        try:
                            stats[stat] = stats.get(stat, 0.0) + sum(float(v) for v in value) / len(value)
                        except (ValueError, TypeError):
                            continue
                    elif isinstance(value, (int, float)):
                        stats[stat] = stats.get(stat, 0.0) + float(value)

        stats["BonusAD"] = bonus_ad
        stats["AD"] += bonus_ad

        # Apply Calibrum's passive range bonus if it's the main hand
        # This is a dynamic effect, so it might be better handled in the simulation loop
        # or when weapons are equipped. For now, let's add it here if Calibrum is initial.
        if self.main_hand.name == "Calibrum" and "bonus_range" in self.main_hand.passive_effect:
            stats["AttackRange"] += self.main_hand.passive_effect["bonus_range"]

        # Cap crit chance at 100%
        stats["Crit"] = min(stats["Crit"], 1.0)

        # Apply Infinity Edge bonus (40% crit damage)
        if has_infinity_edge:
            stats["CritDmg"] += 0.4

        return stats

    def apply_magic_mitigation(self, damage, enemy_mr_value=50.0): # Added enemy_mr_value parameter
        """
        Applies magic resistance mitigation to incoming magic damage.
        
        Parameters:
        damage (float): Raw magic damage before mitigation
        enemy_mr_value (float): Enemy's current magic resistance
        
        Returns:
        float: Mitigated magic damage
        """
        # Apply magic penetration
        effective_mr = max(0, enemy_mr_value - self.stats.get("MagicPen", 0))
        
        # Apply magic resistance formula
        if effective_mr >= 0:
            mitigated_damage = damage * (100 / (100 + effective_mr))
        else:
            # Negative MR increases damage
            mitigated_damage = damage * (2 - (100 / (100 - effective_mr)))
            
        return mitigated_damage

    def rotate_weapon(self):
        # Proper rotation delay from PDF (Note: research.txt mentions 1s assembly, 1.5s ability CD)
        # The existing ROTATION_DELAY = 0.3 seems too short for full assembly.
        # Let's use 1.0 for assembly time based on research.txt
        assembly_time = 1.0 
        self.time += assembly_time 
        self.ability_cooldown = max(self.ability_cooldown, self.time + 1.5) # Ability CD after swap

        # Move exhausted weapon to end of queue and reset its ammo
        exhausted_name = self.weapon_queue.popleft()
        self.weapon_queue.append(exhausted_name)
        
        # Reset ammo for the exhausted weapon
        self.weapon_ammo[exhausted_name] = WEAPONS[exhausted_name].moonlight # Reset to full
        
        # Update current weapons
        self.main_hand_name = self.weapon_queue[0]
        self.off_hand_name = self.weapon_queue[1]
        self.main_hand = WEAPONS[self.main_hand_name]
        self.off_hand = WEAPONS[self.off_hand_name]

        # Recalculate stats if weapon passives affect them (e.g., Calibrum range)
        # This is a simplified way; a more robust approach would be to have active effects update stats dynamically.
        self.stats = self._calculate_base_stats(tuple(self.item_names)) # Recalculate to apply passives like Calibrum range

        # chakram interaction (from original code)
        self.chakram_stacks = int(self.chakram_stacks * 0.7)  # 30% loss
        # self.time += ROTATION_DELAY # This was redundant if assembly_time is added above

    def calculate_dps(self, duration=500):
        """
        Enhanced DPS calculation with proper weapon cycling and ability usage.
        """
        total_damage = 0.0
        damage_log = []
        ability_uses = 0
        attack_count = 0
        
        # Track weapon usage for more accurate simulation
        weapon_usage = {weapon: 0 for weapon in WEAPONS}
        
        # Reset simulation variables
        self.time = 0.0
        self.ability_cooldown = 0.0
        self.active_chakrams = set()
        self.active_marks = {}
        self.chakram_stacks = 0
        
        # Reset weapon ammo
        self.weapon_ammo = {w: 50 for w in WEAPONS}
        
        while self.time < duration:
            if self.weapon_ammo[self.main_hand.name] <= 0:
                self.rotate_weapon()
            
            # Update attack range based on current main_hand (especially for Calibrum)
            current_attack_range = self.stats["AttackRange"]
            if self.main_hand.name == "Calibrum":
                 current_attack_range = BASE_ATTACK_RANGE + self.main_hand.passive_effect.get("bonus_range",0)
            else: # Reset to base + item bonuses if not Calibrum
                 current_attack_range = BASE_ATTACK_RANGE # This needs to consider item bonuses to range too.
                                                          # _calculate_base_stats should correctly set AttackRange without Calibrum passive initially.
                                                          # Then, here we adjust only for Calibrum.
                 # A better way: self.stats["AttackRange"] is base+items. Add Calibrum bonus if Calibrum is equipped.
                 # This is handled by re-calculating stats in rotate_weapon for now.

            # Track weapon usage
            weapon_usage[self.main_hand.name] += 1
            
            # Calculate attack speed with proper bounds
            attack_speed = min(2.5, BASE_AS * (1 + self.stats.get("AS", 0)))
            attack_time = 1.0 / attack_speed
            
            # Clean up expired chakrams and marks
            self.active_chakrams = {t for t in self.active_chakrams if t > self.time}
            self.active_marks = {t: dmg for t, dmg in self.active_marks.items() if t > self.time}
            self.chakram_stacks = len(self.active_chakrams)
            
            # Initialize crit_occurred_for_infernum before it's potentially used
            crit_occurred_for_infernum = False

            # Advanced logic for when to use abilities
            # Prioritize certain weapon abilities based on situation
            ability_priority = {
                "Infernum": 10,  # Highest priority for AOE damage
                "Crescendum": 8 if self.chakram_stacks < 5 else 5,  # Priority changes with stacks
                "Calibrum": 7,
                "Gravitum": 6,
                "Severum": 5 if self.stats.get("LS", 0) < 0.1 else 3  # Priority changes with lifesteal
            }
            
            # Check if ability is available
            can_use_ability = (self.time >= self.ability_cooldown) and (self.weapon_ammo[self.main_hand.name] >= 10)
            
            # Intelligent ability usage based on weapon and situation
            should_use_ability = (
                ability_priority.get(self.main_hand.name, 5) > 5 or  # High priority weapon
                (self.main_hand.name == "Crescendum" and self.chakram_stacks < 5) or  # Need more chakrams
                (self.main_hand.name == "Severum" and self.stats.get("LS", 0) < 0.1)  # Need healing
            )
            
            if can_use_ability and should_use_ability:
                # Use ability
                damage = self.simulate_ability()
                total_damage += damage
                damage_log.append((self.time, "ability", self.main_hand.name, damage))
                ability_uses += 1
                self.ability_cooldown = self.time + ABILITY_COOLDOWN
                self.time += ABILITY_CAST_TIME
            else:
                # Regular attack
                damage = self.simulate_attack()
                total_damage += damage
                damage_log.append((self.time, "attack", self.main_hand.name, damage))
                attack_count += 1
                self.time += attack_time
        
        # More accurate DPS calculation
        avg_dps = total_damage / duration if duration > 0 else 0
        
        # Additional stats that could be returned for analysis
        stats = {
            "ability_percentage": ability_uses / (ability_uses + attack_count) if (ability_uses + attack_count) > 0 else 0,
            "weapon_distribution": {w: count / sum(weapon_usage.values()) for w, count in weapon_usage.items()},
            "total_damage": total_damage,
            "ability_uses": ability_uses,
            "attack_count": attack_count
        }
        
        return avg_dps

    def simulate_attack(self):
        """
        Enhanced attack simulation with improved weapon mechanics and item interactions.
        """
        crit_occurred_for_infernum = False # Initialize to ensure it's always defined
        if self.weapon_ammo[self.main_hand.name] <= 0:
            self.rotate_weapon()
            # After rotating, self.main_hand and self.off_hand are updated
        
        self.use_ammo(1) # Consumes 1 ammo for the attack

        target_health = self.enemy_health # Current health of the target for certain effects

        total_ad = self.stats["AD"] # Total AD from base + items + BonusAD stat

        physical_damage = 0.0
        magic_damage = 0.0
        true_damage = 0.0

        # --- Base Physical Damage from Auto Attack ---
        # Most weapons deal 100% AD, Infernum is an exception via its passive.
        base_attack_damage = total_ad
        
        if self.main_hand.name == "Infernum":
            base_attack_damage *= self.main_hand.passive_effect.get("primary_target_damage_mod", 1.0)

        physical_damage += base_attack_damage

        # --- Apply Main-Hand Weapon's On-Hit and Passive Effects ---
        weapon_name = self.main_hand.name
        
        # Crescendum: AD scaling per chakram stack
        if weapon_name == "Crescendum":
            chakram_ad_bonus = self.chakram_stacks * self.main_hand.passive_effect.get("bonus_ad_per_chakram_stack", 0.0) # e.g., 0.02 AD per stack
            physical_damage += chakram_ad_bonus * total_ad # This bonus applies to the AD part of the attack
            # Crescendum on-hit also generates a chakram stack upon return
            if self.main_hand.on_hit_effect.get("generates_chakram_on_return"):
                self.chakram_stacks = min(self.main_hand.passive_effect.get("max_chakrams", 20), self.chakram_stacks + 1)
                # Add to active_chakrams set if detailed tracking is needed for duration

        # Calibrum: Consuming a mark from a previous ability hit
        # This is a special attack type, usually triggered by right-clicking a marked target.
        # For simplicity, we'll assume if a mark is active and Calibrum is attacking, it tries to consume it.
        # A more detailed simulation would have a separate "empowered_calibrum_attack"
        if weapon_name == "Calibrum":
            # Check active_marks for a mark applied by Calibrum's Q (Moonshot)
            # This part of the logic needs to be carefully integrated with how marks are applied and timed out.
            # For now, let's assume a mark is available if Calibrum Q was used recently.
            # The on_hit_effect for Calibrum is for this empowered attack.
            if self.active_marks.get(weapon_name, 0) > self.time : # Check if a Calibrum mark is active
                mark_details = self.main_hand.on_hit_effect
                if mark_details.get("consumes_mark"):
                    physical_damage += mark_details.get("mark_consume_bonus_damage_flat", 0)
                    physical_damage += mark_details.get("mark_consume_bonus_damage_bonus_ad_ratio", 0) * self.stats["BonusAD"]
                    # Mark is consumed
                    self.active_marks.pop(weapon_name, None)
                    # This attack would also use the special range, not simulated here directly for DPS calc.

        # Severum: Healing from basic attacks (passive effect)
        if weapon_name == "Severum":
            heal_ratio = self.main_hand.passive_effect.get("heal_from_damage_ratio_lvl18", 0.0)
            # Actual healing would be calculated after damage mitigation on the enemy.
            # For DPS, we focus on damage output. Healing is a secondary stat.

        # Gravitum: Applying slow (on-hit effect)
        if weapon_name == "Gravitum":
            # The slow itself doesn't directly add to DPS but enables other effects (like Q root).
            # Gravitum Q (Binding Eclipse) consumes these marks to root.
            pass # Slow application is an effect, not direct damage.

        # Infernum: Cone damage (on-hit effect)
        if weapon_name == "Infernum":
            # Determine if a critical strike occurs for Infernum's attack, this affects cone properties
            crit_occurred_for_infernum = random.random() < self.stats["Crit"] # This assignment is correct
            cone_details = self.main_hand.on_hit_effect
            num_bolts = cone_details.get("cone_crit_num_bolts", 6) if crit_occurred_for_infernum else cone_details.get("cone_num_bolts", 4)
            # Damage to secondary targets:
            # The primary target damage is already included in base_attack_damage.
            # This is extra damage to other targets in the cone.
            # For single target DPS, this might be 0 unless we model cleave.
            # Assuming 1 primary target, and N-1 secondary targets hit by cone.
            # For simplicity in DPS calc, let's assume it hits 1 additional target with the cone.
            num_secondary_targets_hit_by_cone = 1 
            secondary_damage_ratio = cone_details.get("cone_secondary_target_damage_ratio_lvl18", 1.0)
            
            # Damage dealt by the initial hit (already calculated as base_attack_damage)
            triggering_attack_damage = total_ad * self.main_hand.passive_effect.get("primary_target_damage_mod", 1.0)
            if crit_occurred_for_infernum:
                 triggering_attack_damage *= self.stats["CritDmg"]

            cone_damage_per_secondary_target = triggering_attack_damage * secondary_damage_ratio
            
            # For minions, the ratio is different. Assume champion target here.
            physical_damage += cone_damage_per_secondary_target * num_secondary_targets_hit_by_cone


        # --- Critical Strike ---
        crit_occurred = False # Initialize crit_occurred for the current attack

        if weapon_name == "Infernum":
            # If it's an Infernum attack, its crit status was already determined
            crit_occurred = crit_occurred_for_infernum
            # If Infernum crit, the primary target damage is part of the triggering_attack_damage calculation
            # which should have already factored in the crit multiplier.
            # So, no additional multiplication of physical_damage by CritDmg here for the base hit if it's Infernum.
        elif random.random() < self.stats["Crit"]:
            # For non-Infernum attacks, or if Infernum didn't crit but a general crit roll succeeds (though this logic is a bit redundant here)
            physical_damage *= self.stats["CritDmg"]
            crit_occurred = True
        
        # Ensure that if Infernum's specific crit occurred, the main physical_damage reflects that.
        # The `triggering_attack_damage` in the Infernum block should be the basis for its portion of `physical_damage`.
        # If `crit_occurred_for_infernum` is true, `triggering_attack_damage` (and thus the Infernum part of `physical_damage`)
        # should already be critical. We must avoid double-applying crit damage.

        # Revised crit application for clarity:
        # The base_attack_damage is added to physical_damage initially.
        # If it's Infernum and it crits, its specific cone logic handles the crit implications for cone damage.
        # The primary hit of a critical Infernum attack also crits.

        # Let's refine the critical strike logic to be clearer:
        # 1. Determine if a crit happens for any attack.
        # 2. If Infernum, its specific crit roll (`crit_occurred_for_infernum`) dictates its behavior.

        # Reset physical_damage and rebuild it with crit if applicable
        current_physical_damage = base_attack_damage # Start with the base AD component

        if weapon_name == "Crescendum": # Add chakram bonus before general crit
            chakram_ad_bonus = self.chakram_stacks * self.main_hand.passive_effect.get("bonus_ad_per_chakram_stack", 0.0)
            current_physical_damage += chakram_ad_bonus * total_ad

        # Determine crit status for the main hit
        is_critical_hit = False
        if weapon_name == "Infernum":
            is_critical_hit = crit_occurred_for_infernum # Now this is safe
        else:
            if random.random() < self.stats["Crit"]:
                is_critical_hit = True

        if is_critical_hit:
            current_physical_damage *= self.stats["CritDmg"]
            crit_occurred = True # Set the general flag

        physical_damage = current_physical_damage # Assign the calculated physical damage

        # Add Calibrum mark consumption damage (this is bonus damage, typically doesn't crit with the main hit)
        if weapon_name == "Calibrum":
            if self.active_marks.get(weapon_name, 0) > self.time:
                mark_details = self.main_hand.on_hit_effect
                if mark_details.get("consumes_mark"):
                    physical_damage += mark_details.get("mark_consume_bonus_damage_flat", 0)
                    physical_damage += mark_details.get("mark_consume_bonus_damage_bonus_ad_ratio", 0) * self.stats["BonusAD"]
                    self.active_marks.pop(weapon_name, None)
        
        # Add Infernum cone damage (calculated based on its own crit status)
        if weapon_name == "Infernum":
            cone_details_recheck = self.main_hand.on_hit_effect
            triggering_damage_for_cone = total_ad * self.main_hand.passive_effect.get("primary_target_damage_mod", 1.0)
            if crit_occurred_for_infernum: # Now this is safe
                 triggering_damage_for_cone *= self.stats["CritDmg"]

            cone_damage_per_secondary = triggering_damage_for_cone * cone_details_recheck.get("cone_secondary_target_damage_ratio_lvl18", 1.0)
            num_secondary_targets_hit_by_cone = 1
            physical_damage += cone_damage_per_secondary * num_secondary_targets_hit_by_cone

        # --- Item On-Hit Effects ---
        for item_name in self.item_names:
            item = ITEMS.get(item_name, {})
            if "OnHitMagicDamage" in item:
                magic_damage += item["OnHitMagicDamage"]
            if "OnHitCurrentHealth" in item: # e.g., Blade of the Ruined King
                # This is % of *target's current health*. For DPS calc, this is tricky.
                # Using a fixed estimate or average. Let's assume target is at 50% HP for an average.
                estimated_target_current_health = self.enemy_health * 0.5 
                physical_damage += estimated_target_current_health * item["OnHitCurrentHealth"]
            if item_name == "Kraken Slayer":
                # Kraken Slayer procs every 3rd attack.
                # This needs a counter in the simulator state. For now, average it out.
                # (BonusPhysicalDamage is a tuple in ITEMS, take the first value)
                kraken_damage = item.get("BonusPhysicalDamage", [0,0])[0] 
                true_damage += kraken_damage / 3 
            if item_name == "Muramana": # Shock passive
                # AD: 2.5% max mana. Abilities: 6% max mana + 2.5% bonus AD
                # For basic attacks:
                physical_damage += self.stats["Mana"] * 0.015 # research: 1.5% max mana as bonus physical
                physical_damage += total_ad * 0.027 # research: 2.7% AD as bonus physical
                                
            # Navori Flickerblade (Quickblades): Cooldown reduction on crit
            if item_name == "Navori Flickerblade" and crit_occurred:
                # Reduces basic ability cooldowns by 15% of remaining CD
                # This affects self.ability_cooldown.
                reduction_percentage = item.get("CooldownReduction", 0.15)
                remaining_cooldown = max(0, self.ability_cooldown - self.time)
                self.ability_cooldown -= remaining_cooldown * reduction_percentage
            
            # Trinity Force Spellblade: after ability, next attack +200% base AD
            # This needs tracking of "spellblade ready" state. Assume 50% proc rate for simplicity.
            if item_name == "Trinity Force" and random.random() < 0.5:
                 physical_damage += BASE_AD_LEVEL18 * item.get("SpellbladeDamage", 2.0)


        # --- Weapon Synergy Multipliers (applied to the weapon's portion of damage) ---
        # This is complex. Synergies often modify how abilities work or add utility.
        # The "multiplier" in WEAPON_SYNERGIES seems like a general DPS boost.
        # Let's apply it to the physical damage portion derived from the weapon itself.
        synergy_key = (self.main_hand.name, self.off_hand.name)
        if synergy_key not in WEAPON_SYNERGIES:
            synergy_key = (self.off_hand.name, self.main_hand.name)
        
        if synergy_key in WEAPON_SYNERGIES:
            synergy_multiplier = WEAPON_SYNERGIES[synergy_key].get("multiplier", 1.0)
            physical_damage *= synergy_multiplier # Apply to total physical before mitigation for now

        # --- Damage Mitigation ---
        final_physical_damage = apply_physical_mitigation(
            physical_damage,
            self.enemy_armor,
            self.stats.get("ArmorPen", 0.0),
            self.stats.get("Lethality", 0.0)
        )
        final_magic_damage = self.apply_magic_mitigation(magic_damage, enemy_mr_value=self.enemy_mr) # Use self.enemy_mr

        total_damage_this_attack = final_physical_damage + final_magic_damage + true_damage
        
        # --- Post-Attack Effects (e.g., Lifesteal) ---
        if self.stats.get("LS", 0.0) > 0:
            heal_from_lifesteal = total_damage_this_attack * self.stats["LS"]
            # This healing would affect Aphelios's health, not directly DPS.

        # Severum passive healing (applied on its own damage dealt)
        if weapon_name == "Severum":
            severum_heal_ratio = self.main_hand.passive_effect.get("heal_from_damage_ratio_lvl18", 0.0)
            # Heal is based on post-mitigation damage dealt by Severum's attack portion
            # This is complex to isolate. For now, assume it heals based on total_damage_this_attack if Severum is main.
            # A more accurate model would track damage sources.

        return total_damage_this_attack

    def simulate_ability(self):
        """
        Enhanced ability simulation with proper weapon-specific mechanics and interactions.
        """
        if self.weapon_ammo[self.main_hand.name] < self.main_hand.ability_details.get("cost", 10): # Check cost
            # Not enough ammo, should not happen if can_use_ability was checked before calling
            return 0.0 
        
        self.use_ammo(self.main_hand.ability_details.get("cost", 10))
        
        total_ad = self.stats["AD"]
        bonus_ad = self.stats["BonusAD"]
        ap_stat = self.stats.get("Ability Power", 0) # Assuming AP is a stat if built

        weapon = self.main_hand
        off_hand_weapon = self.off_hand
        ability_details = weapon.ability_details

        raw_physical_damage = 0.0
        raw_magic_damage = 0.0
        # true_damage_from_ability = 0.0 # Usually abilities don't do true, but for completeness

        # --- Calculate Base Damage from Ability Ratios ---
        base_dmg = ability_details.get("base_damage_lvl18", 0.0)
        bonus_ad_ratio = ability_details.get("bonus_ad_ratio", 0.0)
        total_ad_ratio = ability_details.get("total_ad_ratio", 0.0) # If ability scales with total AD
        ap_ratio = ability_details.get("ap_ratio", 0.0)

        current_raw_damage = base_dmg + (bonus_ad * bonus_ad_ratio) + (total_ad * total_ad_ratio) + (ap_stat * ap_ratio)

        if ability_details.get("damage_type", "physical") == "physical":
            raw_physical_damage += current_raw_damage
        elif ability_details.get("damage_type", "physical") == "magic":
            raw_magic_damage += current_raw_damage

        # --- Weapon-Specific Ability Effects & Damage Adjustments ---
        if weapon.name == "Calibrum": # Moonshot
            if ability_details.get("applies_mark"):
                self.active_marks[weapon.name] = self.time + ability_details.get("mark_duration", 4.5)
            # Moonshot itself is just damage, mark enables next auto.

        elif weapon.name == "Severum": # Onslaught
            # Onslaught performs multiple attacks. Each attack deals damage.
            # Damage per hit: base + bonus_ad_ratio
            onslaught_hit_base = ability_details.get("attack_base_damage_lvl18", 0)
            onslaught_hit_bonus_ad_ratio = ability_details.get("attack_bonus_ad_ratio", 0)
            
            num_attacks = ability_details.get("num_attacks_base", 6)
            # Add attacks from bonus AS: +2 per 100% bonus AS
            num_attacks += int(self.stats.get("AS", 0) / 0.5) # Simplified: research says "2 per 100% bonus AS"
                                                            # Bonus AS is a direct value e.g. 0.35 for 35%
                                                            # So, self.stats.get("AS",0) is bonus AS.
                                                            # num_attacks += int(self.stats.get("AS",0) * 2)

            raw_physical_damage = 0 # Reset, Onslaught is a series of hits
            single_hit_damage = onslaught_hit_base + bonus_ad * onslaught_hit_bonus_ad_ratio
            
            # Onslaught attacks alternate Severum and Off-hand.
            # For simplicity, assume all hits are like Severum's for this calculation,
            # but apply on-hit effectiveness.
            # A full sim would alternate and apply off-hand effects.
            total_onslaught_damage = 0
            for i in range(num_attacks):
                current_hit_damage = single_hit_damage
                # Apply item on-hits at specified effectiveness
                item_on_hit_damage_this_onslaught_hit = 0
                for item_name_in_build in self.item_names:
                    item_data = ITEMS.get(item_name_in_build, {})
                    if "OnHitMagicDamage" in item_data:
                         # Magic damage from item on-hits during Onslaught
                         # This should be mitigated by MR.
                         # For now, adding to raw_physical_damage for simplicity before split.
                         item_on_hit_damage_this_onslaught_hit += item_data["OnHitMagicDamage"] * ability_details.get("on_hit_effectiveness", 0.25)
                
                # Severum passive healing from Onslaught hits
                heal_ratio = weapon.passive_effect.get("ability_heal_from_damage_ratio_lvl18", 0.0)
                # Healing would be based on post-mitigation damage of this hit.

                total_onslaught_damage += (current_hit_damage + item_on_hit_damage_this_onslaught_hit)
            
            raw_physical_damage = total_onslaught_damage
            # Movement speed bonus is utility, not direct DPS.

        elif weapon.name == "Gravitum": # Binding Eclipse
            # Damage is magic (handled by damage_type).
            # Roots enemies marked by Gravitum's slow (utility).
            pass # Damage already calculated based on ratios.

        elif weapon.name == "Infernum": # Duskwave
            # Duskwave deals initial magic damage, then triggers off-hand attacks.
            # Initial hit:
            # raw_magic_damage += base_dmg + bonus_ad * bonus_ad_ratio + ap_stat * ap_ratio 
            # This was already done by the generic calculation.
            
            # Off-hand attacks: This is complex. It's a volley of attacks.
            # For each locked-on target, fires from off-hand.
            # Assume 1 target for DPS. Off-hand attack applies its own effects.
            # This is like a free auto-attack from off-hand.
            # We need to simulate an attack from the off_hand_weapon here.
            # This is a simplified version. A full simulation would be more complex.
            if ability_details.get("triggers_off_hand_attacks"):
                # Simulate a basic attack from the off-hand weapon
                # This is highly simplified. A real off-hand attack would have its own on-hit, crit, etc.
                # For now, let's add its base AD as physical damage.
                # A more accurate simulation would call a simplified simulate_attack for the off-hand.
                off_hand_ad_contribution = self.stats["AD"] # Base damage from off-hand
                # Potentially apply off-hand specific passives if they are simple AD boosts
                # This part needs careful thought to avoid recursive complexity or inaccurate simplification
                raw_physical_damage += off_hand_ad_contribution 

        elif weapon.name == "Crescendum": # Sentry
            if ability_details.get("generates_spectral_chakram_on_cast"):
                self.chakram_stacks = min(weapon.passive_effect.get("max_chakrams", 20), self.chakram_stacks + 1)
                # Add to active_chakrams for duration tracking if needed
                # self.active_chakrams.add(self.time + weapon.passive_effect.get("chakram_duration", 5))
            # Sentry itself (the turret) attacks with off-hand. This is complex to model directly in ability DPS.
            # The ability_details["sentry_attacks_with_off_hand"] = True is a note for that.
            # For now, the damage is primarily from the spectral chakram generation for Crescendum Q's direct impact.
            pass

        # --- Apply Ability-Specific Item Effects (e.g., Muramana for abilities) ---
        for item_name in self.item_names:
            item = ITEMS.get(item_name, {})
            if item_name == "Muramana": # Shock passive for abilities
                # research: Abilities: 6% max mana + 2.7% bonus AD (corrected from previous 2.5%)
                # Note: research.txt doesn't explicitly state Muramana's ability proc, this is typical LoL knowledge.
                # Assuming the damage type is physical for Muramana's ability proc.
                muramana_ability_damage = (self.stats.get("Mana", 0) * 0.06) + (self.stats.get("BonusAD", 0) * 0.027)
                raw_physical_damage += muramana_ability_damage

        # --- Damage Mitigation for Ability Damage ---
        final_physical_damage_ability = apply_physical_mitigation(
            raw_physical_damage,
            self.enemy_armor,
            self.stats.get("ArmorPen", 0.0),
            self.stats.get("Lethality", 0.0)
        )
        final_magic_damage_ability = self.apply_magic_mitigation(raw_magic_damage, enemy_mr_value=self.enemy_mr)

        total_damage_this_ability = final_physical_damage_ability + final_magic_damage_ability
        return total_damage_this_ability

# End of ApheliosSimulator class

# ============================================================#
# Simulation Orchestration Functions (moved to global scope)
# ============================================================#

def simulate_build(combo, simulation_duration, enemy_armor, enemy_health):
    try:
        simulator = ApheliosSimulator(combo, enemy_armor=enemy_armor, enemy_health=enemy_health)
        main_weapon = simulator.main_hand.name
        off_weapon = simulator.off_hand.name

        damage_synergy = 0.0
        for item_name in combo: # Iterate over names, then get from ITEMS
            if item_name not in ITEMS:
                print(f"Warning: Item {item_name} not found in ITEMS dictionary.")
                continue
            item_stats = ITEMS[item_name]
            for stat, value in item_stats.items():
                if stat == "name":
                    continue
                if isinstance(value, tuple):
                    # Attempt to average, ensure values are floatable
                    try:
                        value = sum(float(v) for v in value) / len(value)
                    except (ValueError, TypeError):
                        # print(f"Warning: Could not process tuple value {value} for stat {stat} in item {item_name}")
                        continue # Skip if not processable
                if isinstance(value, (int, float)):
                    weapon_suitability = (
                        WEAPON_DAMAGE_FACTORS[main_weapon].get(stat, 0.0) * 0.7 +
                        WEAPON_DAMAGE_FACTORS[off_weapon].get(stat, 0.0) * 0.3
                    )
                    damage_synergy += float(value) * weapon_suitability

        synergy_key = (main_weapon, off_weapon)
        if synergy_key not in WEAPON_SYNERGIES:
            synergy_key = (off_weapon, main_weapon) # Check reverse order
        
        if synergy_key in WEAPON_SYNERGIES:
            multiplier = WEAPON_SYNERGIES[synergy_key].get("multiplier", 1.0)
            damage_synergy *= multiplier

        dps = simulator.calculate_dps(simulation_duration)
        # Placeholder values for other metrics, can be expanded later
        health_scaling = 0.0 
        armor_mr_rating = 0.0
        mobility_factor = simulator.stats.get("MoveSpeed", BASE_MOVE_SPEED) * 0.01
        life_steal_rating = simulator.stats.get("LS", 0.0)
        omnivamp_rating = simulator.stats.get("Omnivamp", 0.0)

        total_score = dps * 10 + damage_synergy * 5 # Example scoring

        return (combo, total_score, dps, damage_synergy, health_scaling, armor_mr_rating, mobility_factor, life_steal_rating, omnivamp_rating)
    except Exception as e:
        print(f"Error during simulation for {combo}: {e}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging
        return (combo, 0, 0, 0, 0, 0, 0, 0, 0)

def simulate_build_chunk(builds_chunk, simulation_duration, enemy_armor, enemy_health):
    results = []
    for combo in builds_chunk:
        result = simulate_build(combo, simulation_duration, enemy_armor, enemy_health)
        results.append(result)
    return results

def optimize_aphelios_build(simulation_duration=900, enemy_armor=200, enemy_health=3000, chunk_size=500):
    # Generate only valid item combinations
    item_keys = list(ITEMS.keys())
    item_combos = [
        combo for combo in itertools.combinations(item_keys, 5) # Use item_keys
        if is_valid_build(combo)
    ]
    
    if not item_combos:
        print("No valid item combinations found.")
        return []

    # Use the globally defined chunkify
    chunks = list(chunkify(item_combos, chunk_size))
    all_results = []
    print(f"Testing {len(item_combos)} valid builds in {len(chunks)} chunks.")

    # Ensure ProcessPoolExecutor is used correctly, os.cpu_count() might need to be capped or handled if None
    num_workers = os.cpu_count()
    if num_workers is None or num_workers == 0:
        num_workers = 1 # Fallback to at least one worker

    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [
            executor.submit(simulate_build_chunk, chunk, simulation_duration, enemy_armor, enemy_health)
            for chunk in chunks
        ]
        
        for future in concurrent.futures.as_completed(futures):
            try:
                chunk_results = future.result()
                all_results.extend(chunk_results)
            except Exception as e:
                print(f"Error processing chunk: {e}")
                import traceback
                traceback.print_exc()
                continue

    return sorted(all_results, key=lambda x: (-x[1] if len(x) > 1 else 0, -x[2] if len(x) > 2 else 0))

# ============================================================#
# Main execution block (example)
# ============================================================#
if __name__ == "__main__":
    print("Starting Aphelios Build Optimization...")
    # Example: Optimize for a standard scenario
    # These parameters can be adjusted or taken from command-line arguments
    duration = 60  # Shorter duration for quicker testing, adjust as needed (e.g., 600-900s for full rotations)
    enemy_armor_val = 150
    enemy_health_val = 2500
    build_chunk_size = 200 # Smaller chunk size for more responsive feedback during testing

    top_builds = optimize_aphelios_build(
        simulation_duration=duration,
        enemy_armor=enemy_armor_val,
        enemy_health=enemy_health_val,
        chunk_size=build_chunk_size
    )

    print("\nTop Aphelios Builds:")
    if top_builds:
        for i, build_info in enumerate(top_builds[:10]): # Print top 10 builds
            combo, score, dps, syn, *_ = build_info # Unpack carefully
            print(f"{i+1}. Build: {', '.join(combo)}")
            print(f"   Score: {score:.2f}, DPS: {dps:.2f}, Synergy: {syn:.2f}")
    else:
        print("No builds were successfully simulated or ranked.")

    # Example of simulating a single, specific build for detailed analysis
    specific_build = ("Kraken Slayer", "Infinity Edge", "Lord Dominik's Regards", "Bloodthirster", "Phantom Dancer")
    if is_valid_build(specific_build):
        print(f"\nSimulating specific build: {', '.join(specific_build)}")
        simulator_instance = ApheliosSimulator(list(specific_build), enemy_armor=enemy_armor_val, enemy_health=enemy_health_val)
        detailed_dps = simulator_instance.calculate_dps(duration=duration) # Use the same duration for comparison
        print(f"Calculated DPS for specific build: {detailed_dps:.2f}")
        # You could add more detailed logging from the simulator instance here if needed
        # For example, print simulator_instance.stats or weapon usage logs
    else:
        print(f"\nSpecific build {', '.join(specific_build)} is not valid according to constraints.")