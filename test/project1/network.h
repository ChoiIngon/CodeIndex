#pragma once
#include <string>
#include <functional>

namespace GameServer {
namespace Network {

enum class ConnectionStatus {
    Disconnected,
    Connecting,
    Connected,
    Failed,
};

class NetworkManager {
public:
    static NetworkManager& Instance();

    bool ConnectToServer(const std::string& host, int port);

    void HandleConnectionFailure(int sessionId, int errorCode);

    void ForceDisconnect(int sessionId, const std::string& reason);

    bool SendPacket(int sessionId, const void* data, int size);

    ConnectionStatus GetStatus(int sessionId) const;

    bool RetryConnection(int sessionId, int maxRetries = 3);

    void SetOnDisconnectCallback(std::function<void(int)> callback);

private:
    NetworkManager() = default;
    int m_maxSessions = 10000;
};

}
}
