// Project2 Data Pipeline - Header File
#ifndef DATA_PIPELINE_H
#define DATA_PIPELINE_H

#include <string>
#include <vector>
#include <queue>
#include <memory>
#include <functional>
#include <future>
#include <mutex>
#include <condition_variable>
#include <atomic>
#include <chrono>
#include <map>

namespace Pipeline {
    
    enum class DataFormat {
        JSON,
        XML,
        CSV,
        Binary,
        Protobuf
    };
    
    enum class ProcessingStage {
        Input,
        Validation,
        Transformation,
        Aggregation,
        Output,
        Error
    };
    
    struct DataPacket {
        std::string id;
        std::vector<uint8_t> payload;
        DataFormat format;
        ProcessingStage stage;
        std::chrono::high_resolution_clock::time_point timestamp;
        std::string sourceId;
        size_t size;
        
        DataPacket() : format(DataFormat::JSON), stage(ProcessingStage::Input), size(0) {
            timestamp = std::chrono::high_resolution_clock::now();
        }
    };
    
    struct PipelineMetrics {
        size_t totalProcessed;
        size_t totalErrors;
        size_t queueSize;
        double throughputPerSecond;
        std::chrono::milliseconds averageProcessingTime;
        std::chrono::high_resolution_clock::time_point lastUpdate;
        
        PipelineMetrics() : totalProcessed(0), totalErrors(0), queueSize(0), throughputPerSecond(0.0) {
            lastUpdate = std::chrono::high_resolution_clock::now();
        }
    };
    
    class DataProcessor {
    public:
        virtual ~DataProcessor() = default;
        virtual bool processPacket(DataPacket& packet) = 0;
        virtual std::string getProcessorName() const = 0;
        virtual bool configure(const std::string& config) = 0;
    };
    
    class DataValidator : public DataProcessor {
    public:
        DataValidator();
        virtual ~DataValidator();
        
        bool processPacket(DataPacket& packet) override;
        std::string getProcessorName() const override;
        bool configure(const std::string& config) override;
        
        void addValidationRule(const std::string& rule);
        void removeValidationRule(const std::string& rule);
        std::vector<std::string> getValidationErrors() const;
        
    private:
        std::vector<std::string> validationRules;
        std::vector<std::string> lastErrors;
        bool validatePacket(const DataPacket& packet);
    };
    
    class DataTransformer : public DataProcessor {
    public:
        DataTransformer();
        virtual ~DataTransformer();
        
        bool processPacket(DataPacket& packet) override;
        std::string getProcessorName() const override;
        bool configure(const std::string& config) override;
        
        void addTransformation(const std::string& name, std::function<bool(DataPacket&)> transform);
        void removeTransformation(const std::string& name);
        std::vector<std::string> getTransformationNames() const;
        
    private:
        std::map<std::string, std::function<bool(DataPacket&)>> transformations;
        bool applyTransformations(DataPacket& packet);
    };
    
    class DataAggregator : public DataProcessor {
    public:
        DataAggregator();
        virtual ~DataAggregator();
        
        bool processPacket(DataPacket& packet) override;
        std::string getProcessorName() const override;
        bool configure(const std::string& config) override;
        
        void setAggregationWindow(std::chrono::milliseconds window);
        void setBatchSize(size_t batchSize);
        std::vector<DataPacket> getAggregatedBatch();
        
    private:
        std::vector<DataPacket> aggregationBuffer;
        std::chrono::milliseconds windowSize;
        size_t maxBatchSize;
        std::chrono::high_resolution_clock::time_point windowStart;
        
        bool shouldFlushBatch() const;
        void flushBatch();
    };
    
    class DataPipeline {
    private:
        std::queue<DataPacket> inputQueue;
        std::queue<DataPacket> outputQueue;
        std::vector<std::unique_ptr<DataProcessor>> processors;
        
        std::mutex inputMutex;
        std::mutex outputMutex;
        std::condition_variable inputCondition;
        std::condition_variable outputCondition;
        
        std::atomic<bool> isRunning;
        std::atomic<bool> shouldStop;
        
        std::vector<std::thread> workerThreads;
        size_t maxWorkers;
        size_t maxQueueSize;
        
        PipelineMetrics metrics;
        std::mutex metricsMutex;
        
    public:
        DataPipeline();
        explicit DataPipeline(size_t maxWorkers);
        ~DataPipeline();
        
        // Pipeline control
        bool start();
        void stop();
        void pause();
        void resume();
        bool isActive() const;
        
        // Processor management
        void addProcessor(std::unique_ptr<DataProcessor> processor);
        void removeProcessor(const std::string& processorName);
        std::vector<std::string> getProcessorNames() const;
        
        // Data flow
        bool enqueueData(const DataPacket& packet);
        bool enqueueData(const std::vector<DataPacket>& packets);
        bool dequeueData(DataPacket& packet);
        std::vector<DataPacket> dequeueData(size_t maxCount);
        
        // Configuration
        void setMaxWorkers(size_t workers);
        void setMaxQueueSize(size_t size);
        void setTimeout(std::chrono::milliseconds timeout);
        
        // Monitoring
        PipelineMetrics getMetrics() const;
        size_t getInputQueueSize() const;
        size_t getOutputQueueSize() const;
        double getThroughput() const;
        
        // Error handling
        void setErrorHandler(std::function<void(const DataPacket&, const std::string&)> handler);
        std::vector<std::string> getRecentErrors(size_t maxCount = 10) const;
        
        // Serialization
        bool saveConfiguration(const std::string& filename) const;
        bool loadConfiguration(const std::string& filename);
        
    private:
        void workerLoop();
        bool processPacket(DataPacket& packet);
        void updateMetrics(const DataPacket& packet, bool success);
        void handleError(const DataPacket& packet, const std::string& error);
        
        std::function<void(const DataPacket&, const std::string&)> errorHandler;
        std::vector<std::string> recentErrors;
        std::mutex errorMutex;
        
        std::chrono::milliseconds processingTimeout;
    };
    
    // Factory functions
    std::unique_ptr<DataPipeline> createDataPipeline(size_t maxWorkers = 4);
    std::unique_ptr<DataValidator> createDataValidator();
    std::unique_ptr<DataTransformer> createDataTransformer();
    std::unique_ptr<DataAggregator> createDataAggregator();
    
    // Utility functions
    std::string dataFormatToString(DataFormat format);
    DataFormat stringToDataFormat(const std::string& format);
    std::string processingStageToString(ProcessingStage stage);
    ProcessingStage stringToProcessingStage(const std::string& stage);
    
    // Predefined transformations
    namespace Transformations {
        bool jsonToCsv(DataPacket& packet);
        bool csvToJson(DataPacket& packet);
        bool compressData(DataPacket& packet);
        bool decompressData(DataPacket& packet);
        bool encryptData(DataPacket& packet, const std::string& key);
        bool decryptData(DataPacket& packet, const std::string& key);
    }
    
    // Predefined validators
    namespace Validators {
        bool validateJsonFormat(const DataPacket& packet);
        bool validateCsvFormat(const DataPacket& packet);
        bool validateDataSize(const DataPacket& packet, size_t maxSize);
        bool validateTimestamp(const DataPacket& packet);
    }
    
} // namespace Pipeline

#endif // DATA_PIPELINE_H