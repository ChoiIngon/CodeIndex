#pragma once
#include "character_stats.h"

namespace GameServer {

int CalculateDamage(const CharacterStats& attacker, const CharacterStats& defender, int skillId);

bool ApplyDamage(CharacterStats& target, int damage);

int CalculateSkillDamage(const CharacterStats& attacker, int skillId, float skillMultiplier);

int CalculateHealAmount(const CharacterStats& caster, int healSkillId);

}
