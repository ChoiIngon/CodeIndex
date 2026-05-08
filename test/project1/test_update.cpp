// 테스트용 업데이트 파일 - C++
#include <string>
#include <iostream>

class TestClass {
public:
    std::string testFunction() {
        return "version 1";
    }
    
    int getValue() {
        return value;
    }
    
private:
    int value = 1;
};