#pragma once

namespace GameServer {

struct CharacterStats {
    int maxHp;
    int currentHp;
    int maxMp;
    int currentMp;
    int attackPower;
    int defensePower;
    int speed;
    int level;
    int experience;
    float criticalRate;
    float criticalDamage;
};

struct JobStatBonus {
    int jobId;
    int hpBonus;
    int mpBonus;
    int attackBonus;
    int defenseBonus;
};

struct StatModifier {
    int modifierId;
    float attackMultiplier;
    float defenseMultiplier;
    float speedMultiplier;
    int durationMs;
};

}
