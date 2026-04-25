#pragma once
#include "character_stats.h"
#include <vector>

namespace GameServer {

struct SkillChainStep {
    int skillId;
    float multiplier;
    int cooldown;
    bool requiresCombo;
};

struct SkillChainResult {
    int totalDamage;
    int comboCount;
    bool chainCompleted;
    std::vector<int> hitDamages;
};

SkillChainResult ProcessSkillChain(
    CharacterStats& attacker,
    CharacterStats& defender,
    const std::vector<SkillChainStep>& chain,
    int currentComboCount
);

std::vector<SkillChainStep> BuildDefaultSkillChain();

}
