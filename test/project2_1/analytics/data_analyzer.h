// Project2 Data Analyzer - Header File
#ifndef DATA_ANALYZER_H
#define DATA_ANALYZER_H

#include <vector>
#include <map>
#include <string>
#include <memory>
#include <fstream>

namespace Analytics {
    
    struct DataPoint {
        double value;
        std::string category;
        long long timestamp;
        std::map<std::string, std::string> metadata;
    };
    
    struct StatisticalSummary {
        double mean;
        double median;
        double standardDeviation;
        double min;
        double max;
        size_t count;
        
        StatisticalSummary();
    };
    
    class DataAnalyzer {
    private:
        std::vector<DataPoint> dataset;
        std::map<std::string, std::vector<double>> categoryData;
        bool isDataLoaded;
        
        // Private helper methods
        DataPoint parseDataLine(const std::string& line);
        void processCategories();
        StatisticalSummary calculateStatistics(const std::vector<double>& values) const;
        double pearsonCorrelation(const std::vector<double>& x, const std::vector<double>& y, size_t n) const;
        void writeStatistics(std::ofstream& file, const StatisticalSummary& stats) const;
        void cleanup();
        
    public:
        DataAnalyzer();
        ~DataAnalyzer();
        
        // Data loading methods
        bool loadDataFromFile(const std::string& filename);
        void addDataPoint(const DataPoint& point);
        void addDataPoint(double value, const std::string& category, long long timestamp = 0);
        
        // Statistical analysis methods
        StatisticalSummary calculateStatistics() const;
        StatisticalSummary calculateCategoryStatistics(const std::string& category) const;
        std::map<std::string, StatisticalSummary> getCategoryBreakdown() const;
        
        // Correlation analysis
        double calculateCorrelation(const std::string& category1, const std::string& category2) const;
        
        // Trend analysis
        std::vector<double> calculateMovingAverage(int windowSize) const;
        
        // Outlier detection
        std::vector<DataPoint> detectOutliers(double threshold = 2.0) const;
        
        // Data export
        bool exportResults(const std::string& filename) const;
        
        // Utility methods
        size_t getDataSize() const;
        std::vector<std::string> getCategories() const;
        void clearData();
    };
    
    // Factory function
    std::unique_ptr<DataAnalyzer> createDataAnalyzer();
    
} // namespace Analytics

#endif // DATA_ANALYZER_H