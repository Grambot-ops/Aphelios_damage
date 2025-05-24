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
BASE_AS = 0.658
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
    Each weapon has a unique set of attributes.
    """
    def __init__(self, name, moonlight, base_damage_mod, on_hit_effect, ability_effect):
        self.name = name
        self.moonlight = moonlight
        self.base_damage_mod = base_damage_mod
        self.on_hit_effect = on_hit_effect
        self.ability_effect = ability_effect

WEAPONS = {
    "Calibrum": MoonstoneWeapon(
        name="Calibrum",
        moonlight=50,
        base_damage_mod=(1.0, 0.2),
        on_hit_effect={"range": 650, "mark_damage": 110},
        ability_effect={"execute": 0.15}
    ),
    "Severum": MoonstoneWeapon(
        name="Severum",
        moonlight=50,
        base_damage_mod=(0.9, 0.0),
        on_hit_effect={"heal": 0.03, "shield_convert": 0.06},
        ability_effect={"lifesteal_boost": 0.25}
    ),
    "Gravitum": MoonstoneWeapon(
        name="Gravitum",
        moonlight=50,
        base_damage_mod=(1.1, 0.0),
        on_hit_effect={"slow": 0.3},
        ability_effect={"root": 1.0}
    ),
    "Infernum": MoonstoneWeapon(
        name="Infernum",
        moonlight=50,
        base_damage_mod=(0.85, 0.15),
        on_hit_effect={"aoe": 0.75},
        ability_effect={"splash": 0.4}
    ),
    "Crescendum": MoonstoneWeapon(
        name="Crescendum",
        moonlight=50,
        base_damage_mod=(0.5, 0.02),
        on_hit_effect={"chakram_gen": 1},
        ability_effect={"chakram_amp": 0.1}
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

def apply_physical_mitigation(damage, enemy_armor, armor_pen=0.0, lethality=0.0):
    level = 18
    lethality_scaled = lethality * (0.6 + 0.4 * (level / 18))
    final_armor = max(0, (enemy_armor * (1 - armor_pen)) - lethality_scaled)
    if final_armor >= 0:
        multiplier = 100 / (100 + final_armor)
    else:
        multiplier = 2 - 100 / (100 - final_armor)
    return damage * multiplier

def apply_magic_mitigation(self, damage):
    """
    Applies magic resistance mitigation to incoming magic damage.
    
    Parameters:
    damage (float): Raw magic damage before mitigation
    
    Returns:
    float: Mitigated magic damage
    """
    # Get enemy magic resistance
    enemy_mr = 50.0  # Default value, you might want to make this configurable
    
    # Apply magic penetration
    effective_mr = max(0, enemy_mr - self.stats.get("MagicPen", 0))
    
    # Apply magic resistance formula
    if effective_mr >= 0:
        mitigated_damage = damage * (100 / (100 + effective_mr))
    else:
        # Negative MR increases damage
        mitigated_damage = damage * (2 - (100 / (100 - effective_mr)))
        
    return mitigated_damage

def rotate_weapon(self):
    # Proper rotation delay from PDF
    self.time += ROTATION_DELAY 
    self.ability_cooldown = max(self.ability_cooldown, self.time + 1.5)

    # Move exhausted weapon to end of queue and reset its ammo
    exhausted = self.weapon_queue.popleft()
    self.weapon_queue.append(exhausted)
    
    # Reset ammo for the exhausted weapon (which is now at the end of the queue)
    self.weapon_ammo[exhausted] = 50  # Reset ammo to full
    
    # Update current weapons
    self.main_hand = WEAPONS[self.weapon_queue[0]]
    self.off_hand = WEAPONS[self.weapon_queue[1]]
    
    # chakram interaction
    self.chakram_stacks = int(self.chakram_stacks * 0.7)  # 30% loss
    self.time += ROTATION_DELAY


# ============================================================
# Aphelios Simulator
# ============================================================
class ApheliosSimulator:
    """Simulates Aphelios' damage output and build performance."""
    def __init__(self, items, enemy_armor=250.0, enemy_health=3500.0, weapon_switch_delay=ROTATION_DELAY, simulate_random=True):
        self.weapon_queue = deque(["Calibrum", "Severum", "Gravitum", "Infernum", "Crescendum"])
        self.main_hand = WEAPONS[self.weapon_queue[0]]
        self.off_hand = WEAPONS[self.weapon_queue[1]]
        self.item_names = items
        self.item_stats = [ITEMS[item] for item in items if item in ITEMS]
        self.stats = self._calculate_base_stats(tuple(items))
        self.enemy_armor = float(enemy_armor)
        self.enemy_health = float(enemy_health)
        self.time = 0.0  # Simulation time in seconds
        self.ability_cooldown = 0.0
        self.weapon_ammo = {w: 50 for w in WEAPONS}
        self.chakram_stacks = 0
        self.active_chakrams = set()
        self.crescendum_return_times = {}
        self.active_marks = {}

    @functools.lru_cache(maxsize=128)
    def _calculate_base_stats(self, items_tuple):
        items = list(items_tuple)
        stats = {
            "AD": BASE_AD_LEVEL18,
            "AS": 0.658,  # Updated from 0.64 to 0.658 (V25.05)
            "Crit": 0.0,
            "CritDmg": DEFAULT_CRIT_DAMAGE,
            "Lethality": 0.0,
            "ArmorPen": 0.0,  # % Armor Penetration (only highest value applies)
            "MagicPen": 0.0,
            "OnHit": 0.0,
            "LS": 0.0,
            "Omnivamp": 0.0,
            "BonusAD": 0.0,
            "AbilityHaste": 0.0,
            "Bonus Range": 0.0,
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

        # Cap crit chance at 100%
        stats["Crit"] = min(stats["Crit"], 1.0)

        # Apply Infinity Edge bonus (40% crit damage)
        if has_infinity_edge:
            stats["CritDmg"] += 0.4

        return stats

    def apply_magic_mitigation(self, damage):
        """
        Applies magic resistance mitigation to incoming magic damage.
        
        Parameters:
        damage (float): Raw magic damage before mitigation
        
        Returns:
        float: Mitigated magic damage
        """
        # Get enemy magic resistance
        enemy_mr = 50.0  # Default value, you might want to make this configurable
        
        # Apply magic penetration
        effective_mr = max(0, enemy_mr - self.stats.get("MagicPen", 0))
        
        # Apply magic resistance formula
        if effective_mr >= 0:
            mitigated_damage = damage * (100 / (100 + effective_mr))
        else:
            # Negative MR increases damage
            mitigated_damage = damage * (2 - (100 / (100 - effective_mr)))
            
        return mitigated_damage
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
            
            # Track weapon usage
            weapon_usage[self.main_hand.name] += 1
            
            # Calculate attack speed with proper bounds
            attack_speed = min(2.5, BASE_AS * (1 + self.stats.get("AS", 0)))
            attack_time = 1.0 / attack_speed
            
            # Clean up expired chakrams and marks
            self.active_chakrams = {t for t in self.active_chakrams if t > self.time}
            self.active_marks = {t: dmg for t, dmg in self.active_marks.items() if t > self.time}
            self.chakram_stacks = len(self.active_chakrams)
            
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
        if self.weapon_ammo[self.main_hand.name] <= 0:
            self.rotate_weapon()
        self.use_ammo(1)

        # Use self.enemy_health and self.enemy_armor directly
        target_health = self.enemy_health

        # Calculate total AD (base + items)
        base_ad = BASE_AD_LEVEL18  
        bonus_ad = self.stats["BonusAD"]
        total_ad = base_ad + bonus_ad

        # Calculate damage components
        physical_damage = 0.0
        magic_damage = 0.0
        true_damage = 0.0

        # Base physical damage with enhanced weapon scaling
        weapon_ad_mod = self.main_hand.base_damage_mod[0]
        
        # Apply Crescendum chakram scaling
        if self.main_hand.name == "Crescendum" and self.chakram_stacks > 0:
            # Progressive scaling based on number of chakrams
            chakram_bonus = min(0.5, self.chakram_stacks * 0.02)  # Cap at 50% bonus
            weapon_ad_mod += chakram_bonus
        
        physical_damage += total_ad * weapon_ad_mod

        # Enhanced weapon-specific effects
        weapon = self.main_hand.name
        off_weapon = self.off_hand.name
        
        # Check for weapon synergy
        synergy_key = (weapon, off_weapon)
        if synergy_key not in WEAPON_SYNERGIES:
            synergy_key = (off_weapon, weapon)
            
        synergy_multiplier = 1.0
        if synergy_key in WEAPON_SYNERGIES:
            synergy_multiplier = WEAPON_SYNERGIES[synergy_key].get("multiplier", 1.0)
        
        # Apply specific weapon mechanics
        if weapon == "Calibrum":
            # Apply mark damage and bonus range
            physical_damage += 110  # Fixed mark damage
            # Check for active marks from previous ability usage
            for mark_time, mark_damage in list(self.active_marks.items()):
                if mark_time > self.time:
                    physical_damage += mark_damage
                    self.active_marks.pop(mark_time, None)
                    break
                    
        elif weapon == "Severum":
            # Apply healing mechanics
            heal_amount = physical_damage * self.main_hand.on_hit_effect.get("heal", 0.03)
            # Apply lifesteal from items and synergies
            if self.stats.get("LS", 0) > 0:
                heal_amount *= (1 + self.stats["LS"])
            
            # Apply synergy healing boost
            if synergy_key in WEAPON_SYNERGIES and "heal_amplifier" in WEAPON_SYNERGIES[synergy_key].get("conditions", {}):
                heal_amount *= WEAPON_SYNERGIES[synergy_key]["conditions"]["heal_amplifier"]
                
        elif weapon == "Gravitum":
            # Apply slow effect and damage multiplier
            slow_value = self.main_hand.on_hit_effect.get("slow", 0.3)
            if synergy_key in WEAPON_SYNERGIES and "slow_amplifier" in WEAPON_SYNERGIES[synergy_key].get("conditions", {}):
                slow_value *= WEAPON_SYNERGIES[synergy_key]["conditions"]["slow_amplifier"]
            
            # Damage bonus from CC
            physical_damage *= (1 + slow_value * 0.1)
            
        elif weapon == "Infernum":
            # Apply AOE damage
            aoe_factor = self.main_hand.on_hit_effect.get("aoe", 0.75)
            targets_hit = 1.6  # Average targets hit by Infernum auto
            
            if synergy_key in WEAPON_SYNERGIES and "splash_radius" in WEAPON_SYNERGIES[synergy_key].get("conditions", {}):
                targets_hit += 0.3  # Better positioning with certain synergies
                
            physical_damage *= (1 + (aoe_factor * (targets_hit - 1)))
            
            # Apply execute mechanic properly (original code mixes it into Infernum incorrectly)
            if "The Collector" in self.item_names and target_health < target_health * 0.05:
                true_damage += target_health * 0.05  # 5% execute
                
        elif weapon == "Crescendum":
            # Enhanced chakram mechanics
            chakram_bonus = self.main_hand.on_hit_effect.get("chakram_gen", 1)
            
            # Generate chakrams from attack
            if synergy_key in WEAPON_SYNERGIES and "chakram_generation" in WEAPON_SYNERGIES[synergy_key].get("conditions", {}):
                chakram_bonus *= WEAPON_SYNERGIES[synergy_key]["conditions"]["chakram_generation"]
                
            # Add new chakram to active set
            for i in range(int(chakram_bonus)):
                self.active_chakrams.add(self.time + 5.0)
            
            # Update chakram stacks
            self.chakram_stacks = len([t for t in self.active_chakrams if t > self.time])
            
            # Additional chakram magic damage
            magic_damage += self.chakram_stacks * 10

        # Apply crits with proper stochastic simulation
        crit_occurred = False
        if random.random() < self.stats["Crit"]:
            crit_multiplier = self.stats["CritDmg"]
            physical_damage *= crit_multiplier
            crit_occurred = True

        # Enhanced item interactions
        for item in self.item_stats:
            item_name = item.get("name", "")
            
            # On-hit magic damage
            if "OnHitMagicDamage" in item:
                magic_damage += item["OnHitMagicDamage"]
                
            # Current health damage (BotRK)
            if "OnHitCurrentHealth" in item:
                physical_damage += target_health * item["OnHitCurrentHealth"]
                
            # Kraken Slayer implementation
            if item_name == "Kraken Slayer":
                # Simplified implementation - in reality would track auto count
                true_damage += item.get("BonusPhysicalDamage", (150, 200))[0] * 0.33
                
            # Ravenous Hydra cleave
            if "Cleave" in item:
                physical_damage += physical_damage * item["Cleave"] * 0.6  # Assuming hitting 60% of potential targets
                
            # Navori cooldown reduction on crit
            if item_name == "Navori Flickerblade" and crit_occurred:
                cooldown_reduction = item.get("CooldownReduction", 0.15)
                self.ability_cooldown = max(self.time, self.ability_cooldown - cooldown_reduction * 3.0)
                
            # Trinity Force spellblade (proc chance simplified)
            if item_name == "Trinity Force" and random.random() < 0.4:  # 40% chance to proc
                physical_damage += base_ad * item.get("SpellbladeDamage", 2.0)
                
            # Muramana bonus damage on each hit
            if item_name == "Muramana":
                bonus_mana = item.get("Mana", 860.0)
                physical_damage += (bonus_mana * 0.025) + (bonus_ad * 0.05)
                
            # The Collector execute
            if item_name == "The Collector" and target_health < target_health * 0.05:
                true_damage += target_health * 0.05  # 5% execute

        # Apply synergy multiplier
        physical_damage *= synergy_multiplier

        # Mitigation
        physical_damage = apply_physical_mitigation(
            physical_damage,
            self.enemy_armor,
            self.stats["ArmorPen"],
            self.stats["Lethality"]
        )
        
        # Apply magic damage mitigation
        magic_damage = self.apply_magic_mitigation(magic_damage)

        # Final damage calculation
        total_damage = physical_damage + true_damage
        return total_damage

    def simulate_ability(self):
        """
        Enhanced ability simulation with proper weapon-specific mechanics and interactions.
        """
        if self.weapon_ammo[self.main_hand.name] <= 0:
            self.rotate_weapon()
        
        self.use_ammo(10)  # All abilities cost 10 ammo
        
        total_ad = BASE_AD_LEVEL18 + self.stats["BonusAD"]
        weapon = self.main_hand.name
        off_weapon = self.off_hand.name
        
        # Base damage calculation
        raw_ability_damage = total_ad * WEAPONS[weapon].base_damage_mod[1]
        
        # Apply weapon synergy effects
        synergy_key = (weapon, off_weapon)
        if synergy_key not in WEAPON_SYNERGIES:
            synergy_key = (off_weapon, weapon)
        
        synergy_multiplier = 1.0
        if synergy_key in WEAPON_SYNERGIES:
            synergy_multiplier = WEAPON_SYNERGIES[synergy_key].get("multiplier", 1.0)
            # Apply conditional synergy effects
            conditions = WEAPON_SYNERGIES[synergy_key].get("conditions", {})
            for condition, value in conditions.items():
                if condition == "mark_duration" and weapon == "Calibrum":
                    raw_ability_damage *= 1.1  # Enhanced mark damage
                elif condition == "heal_amplifier" and weapon == "Severum":
                    self.stats["LS"] = self.stats.get("LS", 0) * value
                elif condition == "splash_radius" and weapon == "Infernum":
                    raw_ability_damage *= 1.2  # Enhanced splash damage
                elif condition == "turret_range" and weapon == "Crescendum":
                    # Simulate improved turret damage
                    raw_ability_damage *= 1.15
        
        # Enhanced weapon-specific ability effects
        if weapon == "Calibrum":
            # Mark application
            self.active_marks[self.time + 5.0] = total_ad * 0.4
            raw_ability_damage *= 1.25  # Long-range bonus
            
            # Apply execute effect
            execute_threshold = WEAPONS[weapon].ability_effect.get("execute", 0.15)
            if self.enemy_health < self.enemy_health * execute_threshold:
                raw_ability_damage *= 1.3  # Enhanced execute damage
                
        elif weapon == "Severum":
            # Enhanced healing mechanics
            healing_amount = raw_ability_damage * WEAPONS[weapon].ability_effect.get("lifesteal_boost", 0.25)
            self.stats["LS"] = self.stats.get("LS", 0) + healing_amount * 0.03
            
            # Bonus attack speed from Severum Q
            self.time -= 0.1  # Slightly faster next action
            
        elif weapon == "Gravitum":
            # Root application
            root_duration = WEAPONS[weapon].ability_effect.get("root", 1.0)
            # Simulate CC value by increasing effective damage
            if synergy_key in WEAPON_SYNERGIES and "root_duration" in WEAPON_SYNERGIES[synergy_key].get("conditions", {}):
                root_duration *= 1.2
            raw_ability_damage *= (1 + root_duration * 0.2)
            
        elif weapon == "Infernum":
            # Enhanced AOE mechanics
            splash_factor = WEAPONS[weapon].ability_effect.get("splash", 0.4)
            targets_hit = 2.5  # Average targets hit by Infernum ability
            
            if synergy_key in WEAPON_SYNERGIES and synergy_key[0] == "Infernum" and synergy_key[1] == "Crescendum":
                targets_hit += 0.5  # Better positioning with this synergy
                
            raw_ability_damage *= (1 + splash_factor) * targets_hit
            
        elif weapon == "Crescendum":
            # Proper chakram mechanics
            base_chakrams = WEAPONS[weapon].on_hit_effect.get("chakram_gen", 1)
            chakram_amp = WEAPONS[weapon].ability_effect.get("chakram_amp", 0.1)
            
            # Generate chakrams
            new_chakrams = base_chakrams
            if synergy_key in WEAPON_SYNERGIES and "chakram_generation" in WEAPON_SYNERGIES[synergy_key].get("conditions", {}):
                new_chakrams *= WEAPON_SYNERGIES[synergy_key]["conditions"]["chakram_generation"]
                
            # Add new chakrams to active set
            for i in range(int(new_chakrams)):
                self.active_chakrams.add(self.time + 5.0)
            
            # Update chakram stacks
            self.chakram_stacks = len([t for t in self.active_chakrams if t > self.time])
            
            # Apply chakram damage scaling
            raw_ability_damage *= (1 + (self.chakram_stacks * chakram_amp))
        
        # Apply item effects on abilities
        for item in self.item_stats:
            item_name = item.get("name", "")
            
            # Apply Infinity Edge crit enhancement to abilities
            if item_name == "Infinity Edge" and random.random() < self.stats["Crit"]:
                raw_ability_damage *= self.stats["CritDmg"]
                
            # Apply The Collector execute
            if item_name == "The Collector" and self.enemy_health < self.enemy_health * 0.05:
                raw_ability_damage += self.enemy_health * 0.05  # Execute damage
                
            # Apply Essence Reaver spellblade
            if item_name == "Essence Reaver":
                raw_ability_damage += self.stats["BonusAD"] * 0.4
        
        # Apply final damage calculation with proper mitigation
        effective_damage = apply_physical_mitigation(
            raw_ability_damage * synergy_multiplier,
            self.enemy_armor,
            self.stats.get("ArmorPen", 0.0),
            self.stats.get("Lethality", 0.0)
        )
        
        return effective_damage

    def use_ammo(self, amount=1):
        self.weapon_ammo[self.main_hand.name] -= amount
        if self.weapon_ammo[self.main_hand.name] <= 0:
            self.rotate_weapon()

    def rotate_weapon(self):
        # Proper rotation delay from PDF
        self.time += ROTATION_DELAY 
        self.ability_cooldown = max(self.ability_cooldown, self.time + 1.5)

        # Move exhausted weapon to end of queue and reset its ammo
        exhausted = self.weapon_queue.popleft()
        self.weapon_queue.append(exhausted)
        
        # Reset ammo for the exhausted weapon (which is now at the end of the queue)
        self.weapon_ammo[exhausted] = 50  # Reset ammo to full
        
        # Update current weapons
        self.main_hand = WEAPONS[self.weapon_queue[0]]
        self.off_hand = WEAPONS[self.weapon_queue[1]]
        
        # chakram interaction
        self.chakram_stacks = int(self.chakram_stacks * 0.7)  # 30% loss
        self.time += ROTATION_DELAY


# ============================================================
# Chunking Helper Function
# ============================================================
def chunkify(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i+chunk_size]

# ============================================================
# Build Simulation Functions
# ============================================================
def simulate_build(combo, simulation_duration, enemy_armor, enemy_health):
    try:
        simulator = ApheliosSimulator(combo, enemy_armor=enemy_armor, enemy_health=enemy_health)
        main_weapon = simulator.main_hand.name
        off_weapon = simulator.off_hand.name

        damage_synergy = 0.0
        for item in combo:
            item_stats = ITEMS[item]
            for stat, value in item_stats.items():
                if stat == "name":
                    continue
                if isinstance(value, tuple):
                    value = sum(float(v) for v in value) / len(value)
                if isinstance(value, (int, float)):
                    weapon_suitability = (
                        WEAPON_DAMAGE_FACTORS[main_weapon].get(stat, 0.0) * 0.7 +
                        WEAPON_DAMAGE_FACTORS[off_weapon].get(stat, 0.0) * 0.3
                    )
                    damage_synergy += float(value) * weapon_suitability

        synergy_key = (main_weapon, off_weapon)
        if synergy_key not in WEAPON_SYNERGIES:
            synergy_key = (off_weapon, main_weapon)
        if synergy_key in WEAPON_SYNERGIES:
            multiplier = WEAPON_SYNERGIES[synergy_key].get("multiplier", 1.0)
            damage_synergy *= multiplier

        dps = simulator.calculate_dps(simulation_duration)
        health_scaling = 0.0
        armor_mr_rating = 0.0
        mobility_factor = simulator.stats["MoveSpeed"] * 0.01
        life_steal_rating = 0.0
        omnivamp_rating = 0.0

        total_score = dps * 10 + damage_synergy * 5

        return (combo, total_score, dps, damage_synergy, health_scaling, armor_mr_rating, mobility_factor, life_steal_rating, omnivamp_rating)
    except Exception as e:
        print(f"Error during simulation for {combo}: {e}")
        return (combo, 0, 0, 0, 0, 0, 0, 0, 0)

def simulate_build_chunk(builds, simulation_duration, enemy_armor, enemy_health):
    results = []
    for combo in builds:
        result = simulate_build(combo, simulation_duration, enemy_armor, enemy_health)
        results.append(result)
    return results

def optimize_aphelios_build(simulation_duration=900, enemy_armor=200, enemy_health=3000, chunk_size=500):
    # Generate only valid item combinations
    item_combos = [
        combo for combo in itertools.combinations(ITEMS.keys(), 5)
        if is_valid_build(combo)
    ]
    
    chunks = list(chunkify(item_combos, chunk_size))
    all_results = []
    print(f"Testing {len(item_combos)} valid builds in {len(chunks)} chunks.")

    with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = [
            executor.submit(simulate_build_chunk, chunk, simulation_duration, enemy_armor, enemy_health)
            for chunk in chunks
        ]
        
        # Improved error handling for futures
        for future in concurrent.futures.as_completed(futures):
            try:
                chunk_results = future.result()
                all_results.extend(chunk_results)
            except Exception as e:
                print(f"Error processing chunk: {e}")
                # Continue with other chunks instead of failing completely
                continue

    return sorted(all_results, key=lambda x: (-x[1], -x[2]))

if __name__ == "__main__":
    top_builds = optimize_aphelios_build()
    print("Top Aphelios Builds:")
    for i, (build, score, dps, damage_synergy, health_scaling, armor_mr_rating, mobility_factor, life_steal_rating, omnivamp_rating) in enumerate(top_builds[:5], 1):
        print(f"{i}. Items: {', '.join(build)}")
        print(f"   DPS: {dps:.1f} | Total Rating: {score:.1f}")
        print(f"   Synergy: {damage_synergy:.1f} | Health Scaling: {health_scaling:.1f}")
        print(f"   Armor/MR: {armor_mr_rating:.1f} | Mobility: {mobility_factor:.1f}")
        print(f"   Lifesteal: {life_steal_rating:.1f} | Omnivamp: {omnivamp_rating:.1f}\n")