#pragma once
#include <vector>

namespace GameServer {
namespace Monster {

struct MonsterInstance {
    int instanceId;
    int templateId;
    int mapId;
    float posX;
    float posY;
    float posZ;
    bool isAlive;
};

struct MonsterSpawnData {
    int monsterId;
    float x;
    float y;
    float z;
    int count;
};

int SpawnMonster(int monsterId, float x, float y, float z, int mapId);

void DespawnMonster(int instanceId);

void SpawnMapMonsters(int mapId, const std::vector<MonsterSpawnData>& spawnList);

void HandleMonsterDeath(int instanceId, int killerPlayerId);

void _ActivateMonsterAI(int instanceId);
void _DeactivateMonsterAI(int instanceId);
void _GenerateDropItems(int instanceId, int killerPlayerId);
void _GrantExpToKiller(int instanceId, int killerPlayerId);

}
}
