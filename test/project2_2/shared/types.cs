// Project1 Shared Types - C#
using System;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;

namespace Project1.Shared.Types
{
    public enum UserRole
    {
        Guest,
        User,
        Admin,
        SuperAdmin
    }
    
    public enum RequestStatus
    {
        Pending,
        Processing,
        Completed,
        Failed,
        Cancelled
    }
    
    public class ApiResponse<T>
    {
        public bool Success { get; set; }
        public string Message { get; set; }
        public T Data { get; set; }
        public DateTime Timestamp { get; set; }
        public Dictionary<string, object> Metadata { get; set; }
        
        public ApiResponse()
        {
            Timestamp = DateTime.UtcNow;
            Metadata = new Dictionary<string, object>();
        }
    }
    
    public class UserProfile
    {
        public int UserId { get; set; }
        
        [Required]
        [StringLength(50)]
        public string Username { get; set; }
        
        [Required]
        [EmailAddress]
        public string Email { get; set; }
        
        [StringLength(100)]
        public string FirstName { get; set; }
        
        [StringLength(100)]
        public string LastName { get; set; }
        
        public UserRole Role { get; set; }
        public bool IsActive { get; set; }
        public DateTime CreatedAt { get; set; }
        public DateTime? LastLoginAt { get; set; }
        
        public string FullName => $"{FirstName} {LastName}".Trim();
    }
    
    public class NetworkRequest
    {
        public string RequestId { get; set; }
        public string Method { get; set; }
        public string Url { get; set; }
        public Dictionary<string, string> Headers { get; set; }
        public string Body { get; set; }
        public RequestStatus Status { get; set; }
        public DateTime CreatedAt { get; set; }
        public TimeSpan? Duration { get; set; }
        
        public NetworkRequest()
        {
            RequestId = Guid.NewGuid().ToString();
            Headers = new Dictionary<string, string>();
            Status = RequestStatus.Pending;
            CreatedAt = DateTime.UtcNow;
        }
    }
    
    public class ConfigurationSettings
    {
        public string ApiBaseUrl { get; set; }
        public string ApiKey { get; set; }
        public int TimeoutSeconds { get; set; }
        public bool EnableLogging { get; set; }
        public string LogLevel { get; set; }
        public Dictionary<string, object> CustomSettings { get; set; }
        
        public ConfigurationSettings()
        {
            TimeoutSeconds = 30;
            EnableLogging = true;
            LogLevel = "Info";
            CustomSettings = new Dictionary<string, object>();
        }
    }
    
    public interface INetworkManager
    {
        Task<ApiResponse<T>> SendRequestAsync<T>(NetworkRequest request);
        void SetConfiguration(ConfigurationSettings config);
        string GetConnectionStatus();
    }
    
    public static class TypeExtensions
    {
        public static bool IsValidEmail(this string email)
        {
            try
            {
                var addr = new System.Net.Mail.MailAddress(email);
                return addr.Address == email;
            }
            catch
            {
                return false;
            }
        }
        
        public static string ToApiJson<T>(this ApiResponse<T> response)
        {
            return System.Text.Json.JsonSerializer.Serialize(response);
        }
    }
}