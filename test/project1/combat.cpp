#include "combat.h"
#include "character_stats.h"
#include <algorithm>
#include <cmath>

namespace GameServer {

int CalculateDamage(const CharacterStats& attacker, const CharacterStats& defender, int skillId) {
    float baseDamage = static_cast<float>(attacker.attackPower);
    float defense = static_cast<float>(defender.defensePower);

    float reducedDamage = baseDamage * (1.0f - defense / (defense + 500.0f));

    bool isCritical = (static_cast<float>(rand()) / RAND_MAX) < attacker.criticalRate;
    if (isCritical) {
        reducedDamage *= attacker.criticalDamage;
    }

    return std::max(1, static_cast<int>(reducedDamage));
}

bool ApplyDamage(CharacterStats& target, int damage) {
    target.currentHp = std::max(0, target.currentHp - damage);
    return target.currentHp == 0;
}

int CalculateSkillDamage(const CharacterStats& attacker, int skillId, float skillMultiplier) {
    int base = CalculateDamage(attacker, CharacterStats{}, skillId);
    return static_cast<int>(base * skillMultiplier);
}

int CalculateHealAmount(const CharacterStats& caster, int healSkillId) {
    return static_cast<int>(caster.maxMp * 0.3f + caster.attackPower * 0.1f);
}

}
