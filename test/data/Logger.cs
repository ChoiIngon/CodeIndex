using System;

namespace GameServer.Common
{
    public enum LogLevel { Debug, Info, Warning, Error, Fatal }

    public interface ILogger
    {
        void LogMessage(LogLevel level, string message);
        void LogError(Exception ex, string context = "");
        void LogWarning(string message);
        void LogDebug(string message);
        void Flush();
    }

    public class ConsoleLogger : ILogger
    {
        public void LogMessage(LogLevel level, string message)
        {
            Console.WriteLine($"[{DateTime.Now:HH:mm:ss}][{level}] {message}");
        }

        public void LogError(Exception ex, string context = "")
        {
            Console.Error.WriteLine($"[ERROR][{context}] {ex.Message}\n{ex.StackTrace}");
        }

        public void LogWarning(string message) => LogMessage(LogLevel.Warning, message);
        public void LogDebug(string message) => LogMessage(LogLevel.Debug, message);
        public void Flush() { }
    }

    public class FileLogger : ILogger
    {
        private readonly string _filePath;

        public FileLogger(string filePath) { _filePath = filePath; }

        public void LogMessage(LogLevel level, string message)
        {
            System.IO.File.AppendAllText(_filePath,
                $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}][{level}] {message}\n");
        }

        public void LogError(Exception ex, string context = "") =>
            LogMessage(LogLevel.Error, $"[{context}] {ex.Message}");

        public void LogWarning(string message) => LogMessage(LogLevel.Warning, message);
        public void LogDebug(string message) => LogMessage(LogLevel.Debug, message);
        public void Flush() { }
    }
}
