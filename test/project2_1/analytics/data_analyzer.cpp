// Project2 Data Analyzer - C++
#include "data_analyzer.h"
#include <iostream>
#include <algorithm>
#include <numeric>
#include <sstream>
#include <cmath>
#include <fstream>

namespace Analytics {
    
    StatisticalSummary::StatisticalSummary() : mean(0), median(0), standardDeviation(0), min(0), max(0), count(0) {}
    
    DataAnalyzer::DataAnalyzer() : isDataLoaded(false) {
        std::cout << "DataAnalyzer initialized" << std::endl;
    }
    
    DataAnalyzer::~DataAnalyzer() {
        cleanup();
    }
    
    // Data loading methods
    bool DataAnalyzer::loadDataFromFile(const std::string& filename) {
        std::ifstream file(filename);
        if (!file.is_open()) {
            std::cerr << "Failed to open file: " << filename << std::endl;
            return false;
        }
        
        std::string line;
        dataset.clear();
        
        while (std::getline(file, line)) {
            DataPoint point = parseDataLine(line);
            dataset.push_back(point);
        }
        
        isDataLoaded = true;
        processCategories();
        std::cout << "Loaded " << dataset.size() << " data points" << std::endl;
        return true;
    }
    
    void DataAnalyzer::addDataPoint(const DataPoint& point) {
        dataset.push_back(point);
        
        // Update category data
        categoryData[point.category].push_back(point.value);
        
        if (!isDataLoaded) {
            isDataLoaded = true;
        }
    }
    
    void DataAnalyzer::addDataPoint(double value, const std::string& category, long long timestamp) {
        DataPoint point;
        point.value = value;
        point.category = category;
        point.timestamp = timestamp;
        addDataPoint(point);
    }
    
    // Statistical analysis methods
    StatisticalSummary DataAnalyzer::calculateStatistics() const {
        if (dataset.empty()) {
            return StatisticalSummary();
        }
        
        std::vector<double> values;
        for (const auto& point : dataset) {
            values.push_back(point.value);
        }
        
        return calculateStatistics(values);
    }
    
    StatisticalSummary DataAnalyzer::calculateCategoryStatistics(const std::string& category) const {
        auto it = categoryData.find(category);
        if (it == categoryData.end()) {
            return StatisticalSummary();
        }
        
        return calculateStatistics(it->second);
    }
    
    std::map<std::string, StatisticalSummary> DataAnalyzer::getCategoryBreakdown() const {
        std::map<std::string, StatisticalSummary> breakdown;
        
        for (const auto& [category, values] : categoryData) {
            breakdown[category] = calculateStatistics(values);
        }
        
        return breakdown;
    }
    
    // Correlation analysis
    double DataAnalyzer::calculateCorrelation(const std::string& category1, const std::string& category2) const {
        auto it1 = categoryData.find(category1);
        auto it2 = categoryData.find(category2);
        
        if (it1 == categoryData.end() || it2 == categoryData.end()) {
            return 0.0;
        }
        
        const auto& values1 = it1->second;
        const auto& values2 = it2->second;
        
        size_t minSize = std::min(values1.size(), values2.size());
        if (minSize < 2) {
            return 0.0;
        }
        
        return pearsonCorrelation(values1, values2, minSize);
    }
    
    // Trend analysis
    std::vector<double> DataAnalyzer::calculateMovingAverage(int windowSize) const {
        std::vector<double> movingAvg;
        
        if (dataset.size() < static_cast<size_t>(windowSize)) {
            return movingAvg;
        }
        
        for (size_t i = windowSize - 1; i < dataset.size(); ++i) {
            double sum = 0.0;
            for (int j = 0; j < windowSize; ++j) {
                sum += dataset[i - j].value;
            }
            movingAvg.push_back(sum / windowSize);
        }
        
        return movingAvg;
    }
    
    // Outlier detection
    std::vector<DataPoint> DataAnalyzer::detectOutliers(double threshold) const {
        std::vector<DataPoint> outliers;
        StatisticalSummary stats = calculateStatistics();
        
        for (const auto& point : dataset) {
            double zScore = std::abs(point.value - stats.mean) / stats.standardDeviation;
            if (zScore > threshold) {
                outliers.push_back(point);
            }
        }
        
        return outliers;
    }
    
    // Data export
    bool DataAnalyzer::exportResults(const std::string& filename) const {
        std::ofstream file(filename);
        if (!file.is_open()) {
            return false;
        }
        
        file << "Data Analysis Results\n";
        file << "===================\n\n";
        
        StatisticalSummary overall = calculateStatistics();
        file << "Overall Statistics:\n";
        writeStatistics(file, overall);
        
        file << "\nCategory Breakdown:\n";
        auto breakdown = getCategoryBreakdown();
        for (const auto& [category, stats] : breakdown) {
            file << "\nCategory: " << category << "\n";
            writeStatistics(file, stats);
        }
        
        return true;
    }
    
    // Utility methods
    size_t DataAnalyzer::getDataSize() const {
        return dataset.size();
    }
    
    std::vector<std::string> DataAnalyzer::getCategories() const {
        std::vector<std::string> categories;
        for (const auto& [category, _] : categoryData) {
            categories.push_back(category);
        }
        return categories;
    }
    
    void DataAnalyzer::clearData() {
        dataset.clear();
        categoryData.clear();
        isDataLoaded = false;
    }
    
    // Private helper methods
    DataPoint DataAnalyzer::parseDataLine(const std::string& line) {
        DataPoint point;
        std::istringstream iss(line);
        
        // Simple CSV parsing: value,category,timestamp
        std::string valueStr, category, timestampStr;
        
        if (std::getline(iss, valueStr, ',') &&
            std::getline(iss, category, ',') &&
            std::getline(iss, timestampStr)) {
            
            point.value = std::stod(valueStr);
            point.category = category;
            point.timestamp = std::stoll(timestampStr);
        }
        
        return point;
    }
    
    void DataAnalyzer::processCategories() {
        categoryData.clear();
        
        for (const auto& point : dataset) {
            categoryData[point.category].push_back(point.value);
        }
    }
    
    StatisticalSummary DataAnalyzer::calculateStatistics(const std::vector<double>& values) const {
        StatisticalSummary summary;
        
        if (values.empty()) {
            return summary;
        }
        
        summary.count = values.size();
        
        // Calculate mean
        summary.mean = std::accumulate(values.begin(), values.end(), 0.0) / values.size();
        
        // Calculate min/max
        auto minmax = std::minmax_element(values.begin(), values.end());
        summary.min = *minmax.first;
        summary.max = *minmax.second;
        
        // Calculate median
        std::vector<double> sortedValues = values;
        std::sort(sortedValues.begin(), sortedValues.end());
        
        size_t mid = sortedValues.size() / 2;
        if (sortedValues.size() % 2 == 0) {
            summary.median = (sortedValues[mid - 1] + sortedValues[mid]) / 2.0;
        } else {
            summary.median = sortedValues[mid];
        }
        
        // Calculate standard deviation
        double variance = 0.0;
        for (double value : values) {
            variance += std::pow(value - summary.mean, 2);
        }
        variance /= values.size();
        summary.standardDeviation = std::sqrt(variance);
        
        return summary;
    }
    
    double DataAnalyzer::pearsonCorrelation(const std::vector<double>& x, const std::vector<double>& y, size_t n) const {
        double sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0, sumY2 = 0;
        
        for (size_t i = 0; i < n; ++i) {
            sumX += x[i];
            sumY += y[i];
            sumXY += x[i] * y[i];
            sumX2 += x[i] * x[i];
            sumY2 += y[i] * y[i];
        }
        
        double numerator = n * sumXY - sumX * sumY;
        double denominator = std::sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
        
        if (denominator == 0) {
            return 0;
        }
        
        return numerator / denominator;
    }
    
    void DataAnalyzer::writeStatistics(std::ofstream& file, const StatisticalSummary& stats) const {
        file << "  Count: " << stats.count << "\n";
        file << "  Mean: " << stats.mean << "\n";
        file << "  Median: " << stats.median << "\n";
        file << "  Std Dev: " << stats.standardDeviation << "\n";
        file << "  Min: " << stats.min << "\n";
        file << "  Max: " << stats.max << "\n";
    }
    
    void DataAnalyzer::cleanup() {
        clearData();
    }
    
    // Factory function
    std::unique_ptr<DataAnalyzer> createDataAnalyzer() {
        return std::make_unique<DataAnalyzer>();
    }
    
} // namespace Analytics