// Project2 Data Utilities - C#
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using System.Xml;
using System.Xml.Linq;
using System.ComponentModel.DataAnnotations;

namespace Project2.Utils
{
    public enum DataFormat
    {
        Json,
        Xml,
        Csv,
        Binary,
        Text
    }
    
    public enum CompressionType
    {
        None,
        GZip,
        Deflate,
        Brotli
    }
    
    public class DataValidationResult
    {
        public bool IsValid { get; set; }
        public List<string> Errors { get; set; }
        public List<string> Warnings { get; set; }
        
        public DataValidationResult()
        {
            Errors = new List<string>();
            Warnings = new List<string>();
        }
    }
    
    public class ProcessingOptions
    {
        public DataFormat InputFormat { get; set; } = DataFormat.Json;
        public DataFormat OutputFormat { get; set; } = DataFormat.Json;
        public CompressionType Compression { get; set; } = CompressionType.None;
        public bool ValidateInput { get; set; } = true;
        public bool PreserveWhitespace { get; set; } = false;
        public Encoding Encoding { get; set; } = Encoding.UTF8;
        public int MaxFileSize { get; set; } = 100 * 1024 * 1024; // 100MB
    }
    
    public static class DataUtils
    {
        private static readonly JsonSerializerOptions DefaultJsonOptions = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            WriteIndented = true,
            PropertyNameCaseInsensitive = true
        };
        
        // File operations
        public static async Task<string> ReadFileAsync(string filePath, Encoding encoding = null)
        {
            if (string.IsNullOrEmpty(filePath))
                throw new ArgumentException("File path cannot be null or empty", nameof(filePath));
            
            if (!File.Exists(filePath))
                throw new FileNotFoundException($"File not found: {filePath}");
            
            encoding ??= Encoding.UTF8;
            
            using var reader = new StreamReader(filePath, encoding);
            return await reader.ReadToEndAsync();
        }
        
        public static async Task WriteFileAsync(string filePath, string content, Encoding encoding = null)
        {
            if (string.IsNullOrEmpty(filePath))
                throw new ArgumentException("File path cannot be null or empty", nameof(filePath));
            
            encoding ??= Encoding.UTF8;
            
            var directory = Path.GetDirectoryName(filePath);
            if (!string.IsNullOrEmpty(directory) && !Directory.Exists(directory))
            {
                Directory.CreateDirectory(directory);
            }
            
            using var writer = new StreamWriter(filePath, false, encoding);
            await writer.WriteAsync(content);
        }
        
        // JSON operations
        public static T DeserializeJson<T>(string json, JsonSerializerOptions options = null)
        {
            if (string.IsNullOrEmpty(json))
                return default(T);
            
            options ??= DefaultJsonOptions;
            return JsonSerializer.Deserialize<T>(json, options);
        }
        
        public static string SerializeJson<T>(T obj, JsonSerializerOptions options = null)
        {
            if (obj == null)
                return "null";
            
            options ??= DefaultJsonOptions;
            return JsonSerializer.Serialize(obj, options);
        }
        
        public static bool IsValidJson(string json)
        {
            if (string.IsNullOrWhiteSpace(json))
                return false;
            
            try
            {
                using var document = JsonDocument.Parse(json);
                return true;
            }
            catch (JsonException)
            {
                return false;
            }
        }
        
        // XML operations
        public static XDocument ParseXml(string xml)
        {
            if (string.IsNullOrEmpty(xml))
                throw new ArgumentException("XML content cannot be null or empty", nameof(xml));
            
            try
            {
                return XDocument.Parse(xml);
            }
            catch (XmlException ex)
            {
                throw new InvalidOperationException($"Failed to parse XML: {ex.Message}", ex);
            }
        }
        
        public static string XmlToJson(string xml)
        {
            var doc = ParseXml(xml);
            var dictionary = XmlToDictionary(doc.Root);
            return SerializeJson(dictionary);
        }
        
        public static bool IsValidXml(string xml)
        {
            if (string.IsNullOrWhiteSpace(xml))
                return false;
            
            try
            {
                XDocument.Parse(xml);
                return true;
            }
            catch (XmlException)
            {
                return false;
            }
        }
        
        // CSV operations
        public static List<Dictionary<string, string>> ParseCsv(string csv, char delimiter = ',')
        {
            if (string.IsNullOrEmpty(csv))
                return new List<Dictionary<string, string>>();
            
            var lines = csv.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
            if (lines.Length == 0)
                return new List<Dictionary<string, string>>();
            
            var headers = ParseCsvLine(lines[0], delimiter);
            var result = new List<Dictionary<string, string>>();
            
            for (int i = 1; i < lines.Length; i++)
            {
                var values = ParseCsvLine(lines[i], delimiter);
                var row = new Dictionary<string, string>();
                
                for (int j = 0; j < Math.Min(headers.Count, values.Count); j++)
                {
                    row[headers[j]] = values[j];
                }
                
                result.Add(row);
            }
            
            return result;
        }
        
        public static string ToCsv<T>(IEnumerable<T> data, char delimiter = ',')
        {
            if (data == null || !data.Any())
                return string.Empty;
            
            var properties = typeof(T).GetProperties();
            var sb = new StringBuilder();
            
            // Write headers
            sb.AppendLine(string.Join(delimiter, properties.Select(p => EscapeCsvField(p.Name))));
            
            // Write data
            foreach (var item in data)
            {
                var values = properties.Select(p => {
                    var value = p.GetValue(item)?.ToString() ?? string.Empty;
                    return EscapeCsvField(value);
                });
                sb.AppendLine(string.Join(delimiter, values));
            }
            
            return sb.ToString();
        }
        
        // Data validation
        public static DataValidationResult ValidateData<T>(T data) where T : class
        {
            var result = new DataValidationResult { IsValid = true };
            
            if (data == null)
            {
                result.IsValid = false;
                result.Errors.Add("Data cannot be null");
                return result;
            }
            
            var validationContext = new ValidationContext(data);
            var validationResults = new List<ValidationResult>();
            
            if (!Validator.TryValidateObject(data, validationContext, validationResults, true))
            {
                result.IsValid = false;
                result.Errors.AddRange(validationResults.Select(vr => vr.ErrorMessage));
            }
            
            return result;
        }
        
        public static bool IsValidFileSize(string filePath, long maxSizeBytes)
        {
            if (!File.Exists(filePath))
                return false;
            
            var fileInfo = new FileInfo(filePath);
            return fileInfo.Length <= maxSizeBytes;
        }
        
        // Encoding utilities
        public static string DetectEncoding(byte[] data)
        {
            if (data == null || data.Length == 0)
                return "UTF-8";
            
            // Simple BOM detection
            if (data.Length >= 3 && data[0] == 0xEF && data[1] == 0xBB && data[2] == 0xBF)
                return "UTF-8";
            
            if (data.Length >= 2 && data[0] == 0xFF && data[1] == 0xFE)
                return "UTF-16LE";
            
            if (data.Length >= 2 && data[0] == 0xFE && data[1] == 0xFF)
                return "UTF-16BE";
            
            return "UTF-8"; // Default assumption
        }
        
        public static byte[] ConvertEncoding(byte[] data, Encoding from, Encoding to)
        {
            if (data == null)
                throw new ArgumentNullException(nameof(data));
            
            if (from.Equals(to))
                return data;
            
            var text = from.GetString(data);
            return to.GetBytes(text);
        }
        
        // Hash and checksums
        public static string CalculateMD5(string input)
        {
            using var md5 = System.Security.Cryptography.MD5.Create();
            var hash = md5.ComputeHash(Encoding.UTF8.GetBytes(input));
            return Convert.ToHexString(hash).ToLowerInvariant();
        }
        
        public static string CalculateSHA256(string input)
        {
            using var sha256 = System.Security.Cryptography.SHA256.Create();
            var hash = sha256.ComputeHash(Encoding.UTF8.GetBytes(input));
            return Convert.ToHexString(hash).ToLowerInvariant();
        }
        
        // Data transformation
        public static async Task<string> ConvertDataFormatAsync(string data, DataFormat from, DataFormat to)
        {
            if (string.IsNullOrEmpty(data))
                return string.Empty;
            
            if (from == to)
                return data;
            
            return (from, to) switch
            {
                (DataFormat.Json, DataFormat.Xml) => JsonToXml(data),
                (DataFormat.Xml, DataFormat.Json) => XmlToJson(data),
                (DataFormat.Json, DataFormat.Csv) => JsonToCsv(data),
                (DataFormat.Csv, DataFormat.Json) => CsvToJson(data),
                _ => throw new NotSupportedException($"Conversion from {from} to {to} is not supported")
            };
        }
        
        // Private helper methods
        private static List<string> ParseCsvLine(string line, char delimiter)
        {
            var result = new List<string>();
            var inQuotes = false;
            var current = new StringBuilder();
            
            for (int i = 0; i < line.Length; i++)
            {
                char c = line[i];
                
                if (c == '"')
                {
                    if (inQuotes && i + 1 < line.Length && line[i + 1] == '"')
                    {
                        current.Append('"');
                        i++; // Skip next quote
                    }
                    else
                    {
                        inQuotes = !inQuotes;
                    }
                }
                else if (c == delimiter && !inQuotes)
                {
                    result.Add(current.ToString());
                    current.Clear();
                }
                else
                {
                    current.Append(c);
                }
            }
            
            result.Add(current.ToString());
            return result;
        }
        
        private static string EscapeCsvField(string field)
        {
            if (string.IsNullOrEmpty(field))
                return string.Empty;
            
            if (field.Contains(',') || field.Contains('"') || field.Contains('\n') || field.Contains('\r'))
            {
                return $"\"{field.Replace("\"", "\"\"\")}\"";
            }
            
            return field;
        }
        
        private static Dictionary<string, object> XmlToDictionary(XElement element)
        {
            var result = new Dictionary<string, object>();
            
            // Add attributes
            foreach (var attr in element.Attributes())
            {
                result[$"@{attr.Name}"] = attr.Value;
            }
            
            // Add elements
            if (element.HasElements)
            {
                foreach (var child in element.Elements())
                {
                    var key = child.Name.LocalName;
                    var value = XmlToDictionary(child);
                    
                    if (result.ContainsKey(key))
                    {
                        if (result[key] is List<object> list)
                        {
                            list.Add(value);
                        }
                        else
                        {
                            result[key] = new List<object> { result[key], value };
                        }
                    }
                    else
                    {
                        result[key] = value;
                    }
                }
            }
            else if (!string.IsNullOrEmpty(element.Value))
            {
                return new Dictionary<string, object> { { "#text", element.Value } };
            }
            
            return result;
        }
        
        private static string JsonToXml(string json)
        {
            var obj = DeserializeJson<Dictionary<string, object>>(json);
            var xml = new XElement("root");
            AddToXml(xml, obj);
            return xml.ToString();
        }
        
        private static void AddToXml(XElement parent, object obj)
        {
            if (obj is Dictionary<string, object> dict)
            {
                foreach (var kvp in dict)
                {
                    var element = new XElement(kvp.Key);
                    AddToXml(element, kvp.Value);
                    parent.Add(element);
                }
            }
            else
            {
                parent.Value = obj?.ToString() ?? string.Empty;
            }
        }
        
        private static string JsonToCsv(string json)
        {
            var array = DeserializeJson<object[]>(json);
            if (array == null || array.Length == 0)
                return string.Empty;
            
            // This is a simplified conversion - assumes array of objects with same structure
            return ToCsv(array.Cast<Dictionary<string, object>>());
        }
        
        private static string CsvToJson(string csv)
        {
            var data = ParseCsv(csv);
            return SerializeJson(data);
        }
    }
}