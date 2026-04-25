#pragma once
#include <string>
#include "character_stats.h"

namespace GameServer {

struct PlayerPosition {
    float x, y, z;
    float yaw;
};

class PlayerManager {
public:
    explicit PlayerManager(int playerId);
    ~PlayerManager();

    bool MovePlayer(int playerId, float destX, float destY, float destZ);

    bool AttackPlayer(int attackerId, int targetId, int skillId);

    PlayerPosition GetPosition(int playerId) const;

    void RestoreHealth(int playerId, int amount);

    void HandlePlayerDeath(int playerId);

private:
    bool _IsPositionValid(float x, float y, float z) const;
    void _BroadcastMove(int playerId, const PlayerPosition& pos);

    int m_playerId;
    PlayerPosition m_position;
    CharacterStats m_stats;
};

}
