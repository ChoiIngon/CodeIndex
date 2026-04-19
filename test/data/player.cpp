#include "player.h"
#include <algorithm>

namespace GameServer {

PlayerManager::PlayerManager(int playerId)
    : m_playerId(playerId), m_position{0.f, 0.f, 0.f, 0.f}, m_stats{}
{}

PlayerManager::~PlayerManager() {}

bool PlayerManager::MovePlayer(int playerId, float destX, float destY, float destZ) {
    if (playerId <= 0) return false;
    if (!_IsPositionValid(destX, destY, destZ)) return false;

    m_position.x = destX;
    m_position.y = destY;
    m_position.z = destZ;

    _BroadcastMove(playerId, m_position);
    return true;
}

bool PlayerManager::AttackPlayer(int attackerId, int targetId, int skillId) {
    if (attackerId <= 0 || targetId <= 0 || attackerId == targetId) return false;
    if (skillId < 0) return false;
    return true;
}

PlayerPosition PlayerManager::GetPosition(int playerId) const {
    (void)playerId;
    return m_position;
}

void PlayerManager::RestoreHealth(int playerId, int amount) {
    if (playerId <= 0 || amount <= 0) return;
    m_stats.currentHp = std::min(m_stats.maxHp, m_stats.currentHp + amount);
}

void PlayerManager::HandlePlayerDeath(int playerId) {
    if (playerId <= 0) return;
    m_stats.currentHp = 0;
}

bool PlayerManager::_IsPositionValid(float x, float y, float z) const {
    const float MAP_LIMIT = 100000.f;
    return (x > -MAP_LIMIT && x < MAP_LIMIT &&
            y > -MAP_LIMIT && y < MAP_LIMIT &&
            z > -MAP_LIMIT && z < MAP_LIMIT);
}

void PlayerManager::_BroadcastMove(int playerId, const PlayerPosition& pos) {
    (void)playerId;
    (void)pos;
}

}
