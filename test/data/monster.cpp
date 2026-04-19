#include "monster.h"
#include <vector>
#include <unordered_map>

namespace GameServer {
namespace Monster {

static std::unordered_map<int, MonsterInstance> g_monsters;
static int g_nextMonsterId = 1;

int SpawnMonster(int monsterId, float x, float y, float z, int mapId) {
    MonsterInstance inst;
    inst.instanceId = g_nextMonsterId++;
    inst.templateId = monsterId;
    inst.mapId = mapId;
    inst.posX = x;
    inst.posY = y;
    inst.posZ = z;
    inst.isAlive = true;

    g_monsters[inst.instanceId] = inst;
    _ActivateMonsterAI(inst.instanceId);
    return inst.instanceId;
}

void DespawnMonster(int instanceId) {
    auto it = g_monsters.find(instanceId);
    if (it == g_monsters.end()) return;

    _DeactivateMonsterAI(instanceId);
    g_monsters.erase(it);
}

void SpawnMapMonsters(int mapId, const std::vector<MonsterSpawnData>& spawnList) {
    for (const auto& data : spawnList) {
        for (int i = 0; i < data.count; ++i) {
            SpawnMonster(data.monsterId, data.x, data.y, data.z, mapId);
        }
    }
}

void HandleMonsterDeath(int instanceId, int killerPlayerId) {
    auto it = g_monsters.find(instanceId);
    if (it == g_monsters.end()) return;

    it->second.isAlive = false;
    _GenerateDropItems(instanceId, killerPlayerId);
    _GrantExpToKiller(instanceId, killerPlayerId);
    DespawnMonster(instanceId);
}

}
}
