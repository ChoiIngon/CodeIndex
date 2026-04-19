#pragma once
#include <vector>
#include <stack>
#include <cassert>

namespace GameServer {
namespace Util {

template<typename T>
class ObjectPool {
public:
    explicit ObjectPool(int initialSize = 64) {
        _Preallocate(initialSize);
    }

    ~ObjectPool() {
        for (T* obj : m_all) {
            delete obj;
        }
    }

    T* Acquire() {
        if (m_free.empty()) {
            T* obj = new T();
            m_all.push_back(obj);
            return obj;
        }
        T* obj = m_free.top();
        m_free.pop();
        return obj;
    }

    void Release(T* obj) {
        assert(obj != nullptr);
        m_free.push(obj);
    }

    int AvailableCount() const { return static_cast<int>(m_free.size()); }
    int TotalCount() const { return static_cast<int>(m_all.size()); }

private:
    void _Preallocate(int count) {
        for (int i = 0; i < count; ++i) {
            T* obj = new T();
            m_all.push_back(obj);
            m_free.push(obj);
        }
    }

    std::vector<T*> m_all;
    std::stack<T*> m_free;
};

}
}
