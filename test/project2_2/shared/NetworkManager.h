// Project1 Network Manager - Header File
#ifndef NETWORK_MANAGER_H
#define NETWORK_MANAGER_H

#include <string>
#include <vector>
#include <map>
#include <memory>
#include <functional>
#include <future>
#include <chrono>

namespace Network {
    
    enum class ConnectionType {
        HTTP,
        HTTPS,
        WebSocket,
        TCP,
        UDP
    };
    
    enum class RequestMethod {
        GET,
        POST,
        PUT,
        DELETE,
        PATCH,
        HEAD,
        OPTIONS
    };
    
    struct NetworkConfig {
        std::string baseUrl;
        std::chrono::seconds timeout;
        int maxRetries;
        bool enableSsl;
        std::map<std::string, std::string> defaultHeaders;
        
        NetworkConfig() : timeout(30), maxRetries(3), enableSsl(true) {}
    };
    
    struct HttpRequest {
        RequestMethod method;
        std::string url;
        std::map<std::string, std::string> headers;
        std::string body;
        std::chrono::seconds timeout;
        
        HttpRequest() : method(RequestMethod::GET), timeout(30) {}
    };
    
    struct HttpResponse {
        int statusCode;
        std::string reasonPhrase;
        std::map<std::string, std::string> headers;
        std::string body;
        std::chrono::milliseconds duration;
        bool success;
        
        HttpResponse() : statusCode(0), success(false) {}
    };
    
    class NetworkManager {
    private:
        NetworkConfig config;
        bool isInitialized;
        std::string userAgent;
        
    public:
        NetworkManager();
        explicit NetworkManager(const NetworkConfig& configuration);
        ~NetworkManager();
        
        // Initialization
        bool initialize(const NetworkConfig& configuration);
        void shutdown();
        bool isConnected() const;
        
        // Synchronous HTTP methods
        HttpResponse get(const std::string& url);
        HttpResponse post(const std::string& url, const std::string& data);
        HttpResponse put(const std::string& url, const std::string& data);
        HttpResponse deleteRequest(const std::string& url);
        HttpResponse sendRequest(const HttpRequest& request);
        
        // Asynchronous HTTP methods
        std::future<HttpResponse> getAsync(const std::string& url);
        std::future<HttpResponse> postAsync(const std::string& url, const std::string& data);
        std::future<HttpResponse> sendRequestAsync(const HttpRequest& request);
        
        // Configuration
        void setBaseUrl(const std::string& url);
        void setTimeout(std::chrono::seconds timeout);
        void setMaxRetries(int retries);
        void addDefaultHeader(const std::string& key, const std::string& value);
        void removeDefaultHeader(const std::string& key);
        
        // Utility methods
        std::string buildUrl(const std::string& endpoint) const;
        std::string encodeUrl(const std::string& url) const;
        bool isValidUrl(const std::string& url) const;
        
        // SSL/TLS
        void enableSsl(bool enable);
        bool verifySslCertificate(const std::string& url);
        
        // Connection pooling
        void setMaxConnections(int maxConn);
        void enableKeepAlive(bool enable);
        
        // Error handling
        std::string getLastError() const;
        void clearLastError();
        
        // Callbacks
        using ProgressCallback = std::function<void(size_t downloaded, size_t total)>;
        void setProgressCallback(ProgressCallback callback);
        
    private:
        // Internal implementation
        HttpResponse executeRequest(const HttpRequest& request);
        bool setupConnection(const std::string& url);
        void processResponse(HttpResponse& response);
        std::string generateUserAgent() const;
        
        // SSL helpers
        bool initializeSsl();
        void cleanupSsl();
        
        // Connection management
        void manageConnections();
        void closeIdleConnections();
        
        std::string lastError;
        ProgressCallback progressCallback;
    };
    
    // Factory functions
    std::unique_ptr<NetworkManager> createNetworkManager();
    std::unique_ptr<NetworkManager> createNetworkManager(const NetworkConfig& config);
    
    // Utility functions
    std::string methodToString(RequestMethod method);
    RequestMethod stringToMethod(const std::string& method);
    bool isHttpsUrl(const std::string& url);
    std::string extractHostname(const std::string& url);
    int extractPort(const std::string& url);
    
} // namespace Network

#endif // NETWORK_MANAGER_H