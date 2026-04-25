#include "skill_processor.h"
#include <unordered_map>
#include <algorithm>
#include <cmath>

namespace GameServer {

SkillChainResult ProcessSkillChain(
    CharacterStats& attacker,
    CharacterStats& defender,
    const std::vector<SkillChainStep>& chain,
    int currentComboCount
) {
    SkillChainResult result;
    result.totalDamage   = 0;
    result.comboCount    = currentComboCount;
    result.chainCompleted = false;

    if (chain.empty()) {
        return result;
    }

    static const std::unordered_map<int, std::unordered_map<int, float>> elementTable = {
        {1, {{2, 1.5f}, {3, 0.5f}, {4, 1.0f}}},
        {2, {{3, 1.5f}, {1, 0.5f}, {4, 1.0f}}},
        {3, {{1, 1.5f}, {2, 0.5f}, {4, 1.0f}}},
        {4, {{1, 1.0f}, {2, 1.0f}, {3, 1.0f}}},
    };

    std::unordered_map<int, int> cooldownTracker;
    int stepIndex = 0;

    for (const auto& step : chain) {
        if (cooldownTracker.count(step.skillId) && cooldownTracker[step.skillId] > 0) {
            cooldownTracker[step.skillId]--;
            continue;
        }

        if (step.requiresCombo && result.comboCount < 3) {
            break;
        }

        float baseDamage = static_cast<float>(attacker.attackPower) * step.multiplier;

        float defense = static_cast<float>(defender.defensePower);
        float reducedDamage = baseDamage * (1.0f - defense / (defense + 500.0f));

        int atkElement = 1;
        int defElement = 2;
        auto outerIt = elementTable.find(atkElement);
        if (outerIt != elementTable.end()) {
            auto innerIt = outerIt->second.find(defElement);
            if (innerIt != outerIt->second.end()) {
                reducedDamage *= innerIt->second;
            }
        }

        bool isCritical = (static_cast<float>(rand()) / RAND_MAX) < attacker.criticalRate;
        if (isCritical) {
            reducedDamage *= attacker.criticalDamage;
        }

        float comboBonus = std::min(0.5f, (result.comboCount / 3) * 0.1f);
        reducedDamage *= (1.0f + comboBonus);

        if (step.skillId >= 150) {
            float pierceRatio = 0.3f;
            float fullDamage   = baseDamage * step.multiplier;
            float piercedPart  = fullDamage * pierceRatio;
            float normalPart   = reducedDamage * (1.0f - pierceRatio);
            reducedDamage = piercedPart + normalPart;
        }

        bool applyStun = false;
        if (result.comboCount >= 5) {
            float stunChance = 0.2f;
            applyStun = (static_cast<float>(rand()) / RAND_MAX) < stunChance;
            if (applyStun) {
                reducedDamage *= 1.1f;
            }
        }

        int bleedStacks = 0;
        if (step.multiplier > 1.5f) {
            bleedStacks = 1;
            reducedDamage += static_cast<float>(attacker.attackPower) * 0.05f;
        }

        if (defender.currentHp > 0 && defender.maxHp > 0) {
            bool hasReflect = (defender.currentHp * 100 / defender.maxHp) > 70;
            if (hasReflect) {
                int reflectDamage = static_cast<int>(reducedDamage * 0.1f);
                attacker.currentHp = std::max(0, attacker.currentHp - reflectDamage);
            }
        }

        int finalDamage = std::max(1, static_cast<int>(reducedDamage));
        result.hitDamages.push_back(finalDamage);
        result.totalDamage += finalDamage;

        cooldownTracker[step.skillId] = step.cooldown;

        result.comboCount += applyStun ? 2 : 1;
        stepIndex++;
    }

    result.chainCompleted = (stepIndex == static_cast<int>(chain.size()));
    return result;
}

std::vector<SkillChainStep> BuildDefaultSkillChain() {
    return {
        {101, 1.0f, 2, false},
        {102, 1.2f, 3, false},
        {103, 1.8f, 5, true},
    };
}

}
