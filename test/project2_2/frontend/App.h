// Project1 Frontend Application - Header File
#ifndef APP_H
#define APP_H

#include <string>
#include <vector>
#include <map>

namespace Frontend {
    
    class App {
    private:
        bool isInitialized;
        bool isRunning = true;
        std::vector<std::string> routes;
        std::map<std::string, std::string> config;
        
    public:
        App();
        ~App();
        
        // Main application lifecycle
        bool initialize();
        void run();
        void stop();
        
        // Configuration
        void setupRoutes();
        void loadConfiguration();
        
        // Internal processing
        void processEvents();
        void update();
        void render();
        void cleanup();
    };
    
} // namespace Frontend

#endif // APP_H