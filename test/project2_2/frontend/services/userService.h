// Project1 User Service - Header File
#ifndef USER_SERVICE_H
#define USER_SERVICE_H

#include <string>
#include <vector>
#include <memory>
#include <future>

namespace Services {
    
    struct UserInfo {
        int id;
        std::string username;
        std::string email;
        std::string firstName;
        std::string lastName;
        bool isActive;
    };
    
    class UserService {
    private:
        std::string baseUrl;
        std::string apiKey;
        
    public:
        UserService(const std::string& url, const std::string& key);
        ~UserService();
        
        // Synchronous methods
        UserInfo getUserById(int userId);
        std::vector<UserInfo> getAllUsers();
        bool createUser(const UserInfo& user);
        bool updateUser(const UserInfo& user);
        bool deleteUser(int userId);
        
        // Asynchronous methods
        std::future<UserInfo> getUserByIdAsync(int userId);
        std::future<std::vector<UserInfo>> getAllUsersAsync();
        std::future<bool> createUserAsync(const UserInfo& user);
        
        // Authentication
        bool authenticateUser(const std::string& username, const std::string& password);
        std::string generateToken(const std::string& username);
        bool validateToken(const std::string& token);
        
        // Configuration
        void setApiKey(const std::string& key);
        void setBaseUrl(const std::string& url);
        std::string getBaseUrl() const;
        
        // Utility methods
        bool isValidEmail(const std::string& email);
        std::string hashPassword(const std::string& password);
        
    private:
        // Internal helper methods
        std::string buildUrl(const std::string& endpoint);
        std::string makeRequest(const std::string& url, const std::string& method, const std::string& data = "");
        UserInfo parseUserJson(const std::string& json);
        std::vector<UserInfo> parseUsersJson(const std::string& json);
    };
    
    // Factory function
    std::unique_ptr<UserService> createUserService(const std::string& configFile);
    
} // namespace Services

#endif // USER_SERVICE_H