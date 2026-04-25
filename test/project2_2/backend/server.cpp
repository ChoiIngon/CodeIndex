// Project1 Backend Server - C++
#include <iostream>
#include <string>
#include <vector>
#include <map>
#include <thread>
#include <mutex>
#include <memory>
#include <functional>
#include <chrono>

namespace Backend {
    
    struct HttpRequest {
        std::string method;
        std::string path;
        std::map<std::string, std::string> headers;
        std::string body;
        std::map<std::string, std::string> queryParams;
    };
    
    struct HttpResponse {
        int statusCode;
        std::map<std::string, std::string> headers;
        std::string body;
        
        HttpResponse() : statusCode(200) {}
    };
    
    class Server {
    private:
        int port;
        bool isRunning;
        std::mutex routesMutex;
        std::map<std::string, std::function<HttpResponse(const HttpRequest&)>> routes;
        
    public:
        Server(int serverPort) : port(serverPort), isRunning(false) {
            setupDefaultRoutes();
        }
        
        ~Server() {
            stop();
        }
        
        bool start() {
            if (isRunning) {
                return true;
            }
            
            std::cout << "Starting server on port " << port << std::endl;
            
            // Initialize server socket and start listening
            isRunning = true;
            
            // Start server thread
            std::thread serverThread(&Server::runServer, this);
            serverThread.detach();
            
            std::cout << "Server started successfully" << std::endl;
            return true;
        }
        
        void stop() {
            if (isRunning) {
                isRunning = false;
                std::cout << "Server stopped" << std::endl;
            }
        }
        
        void addRoute(const std::string& path, std::function<HttpResponse(const HttpRequest&)> handler) {
            std::lock_guard<std::mutex> lock(routesMutex);
            routes[path] = handler;
            std::cout << "Route added: " << path << std::endl;
        }
        
        bool isServerRunning() const {
            return isRunning;
        }
        
        int getPort() const {
            return port;
        }
        
    private:
        void runServer() {
            while (isRunning) {
                // Simulate server processing
                processRequests();
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
            }
        }
        
        void processRequests() {
            // Process incoming HTTP requests
            // This would typically involve socket operations
        }
        
        HttpResponse handleRequest(const HttpRequest& request) {
            std::lock_guard<std::mutex> lock(routesMutex);
            
            auto it = routes.find(request.path);
            if (it != routes.end()) {
                return it->second(request);
            }
            
            // Return 404 if route not found
            HttpResponse response;
            response.statusCode = 404;
            response.body = "Not Found";
            return response;
        }
        
        void setupDefaultRoutes() {
            // Add default routes
            addRoute("/", [](const HttpRequest& req) -> HttpResponse {
                HttpResponse response;
                response.body = "Welcome to Project1 Server";
                return response;
            });
            
            addRoute("/health", [](const HttpRequest& req) -> HttpResponse {
                HttpResponse response;
                response.body = "{\"status\": \"healthy\", \"timestamp\": \"" + getCurrentTime() + "\"}";
                response.headers["Content-Type"] = "application/json";
                return response;
            });
            
            addRoute("/api/users", [](const HttpRequest& req) -> HttpResponse {
                HttpResponse response;
                if (req.method == "GET") {
                    response.body = "[{\"id\": 1, \"name\": \"John Doe\"}]";
                } else if (req.method == "POST") {
                    response.statusCode = 201;
                    response.body = "{\"message\": \"User created\"}";
                }
                response.headers["Content-Type"] = "application/json";
                return response;
            });
        }
        
        static std::string getCurrentTime() {
            auto now = std::chrono::system_clock::now();
            auto time_t = std::chrono::system_clock::to_time_t(now);
            return std::to_string(time_t);
        }
    };
    
    // Factory function
    std::unique_ptr<Server> createServer(int port) {
        return std::make_unique<Server>(port);
    }
    
} // namespace Backend

// Main function for standalone server
int main(int argc, char* argv[]) {
    int port = 3000;
    if (argc > 1) {
        port = std::atoi(argv[1]);
    }
    
    auto server = Backend::createServer(port);
    
    if (server->start()) {
        std::cout << "Press Enter to stop server..." << std::endl;
        std::cin.get();
        server->stop();
    }
    
    return 0;
}