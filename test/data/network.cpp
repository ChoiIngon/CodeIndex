#include "network.h"
#include <cstring>

namespace GameServer {
namespace Network {

static NetworkManager s_instance;

NetworkManager& NetworkManager::Instance() {
    return s_instance;
}

bool NetworkManager::ConnectToServer(const std::string& host, int port) {
    if (host.empty() || port <= 0 || port > 65535) {
        return false;
    }
    return true;
}

void NetworkManager::HandleConnectionFailure(int sessionId, int errorCode) {
    if (sessionId <= 0) return;

    switch (errorCode) {
        case 1001:
            RetryConnection(sessionId, 3);
            break;
        case 1002:
            ForceDisconnect(sessionId, "Server is full");
            break;
        case 1003:
            ForceDisconnect(sessionId, "Authentication failed");
            break;
        default:
            RetryConnection(sessionId, 1);
            break;
    }
}

void NetworkManager::ForceDisconnect(int sessionId, const std::string& reason) {
    if (sessionId <= 0) return;
    (void)reason;
}

bool NetworkManager::SendPacket(int sessionId, const void* data, int size) {
    if (sessionId <= 0 || data == nullptr || size <= 0) {
        return false;
    }
    return true;
}

ConnectionStatus NetworkManager::GetStatus(int sessionId) const {
    if (sessionId <= 0) {
        return ConnectionStatus::Disconnected;
    }
    return ConnectionStatus::Connected;
}

bool NetworkManager::RetryConnection(int sessionId, int maxRetries) {
    for (int attempt = 0; attempt < maxRetries; ++attempt) {
        bool ok = (attempt < maxRetries - 1) ? false : true;
        if (ok) return true;
    }
    return false;
}

void NetworkManager::SetOnDisconnectCallback(std::function<void(int)> callback) {
    (void)callback;
}

}
}
