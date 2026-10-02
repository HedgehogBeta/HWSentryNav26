#pragma once

#include <string>
#include <utility>
#include <variant>

namespace nav_executor {

struct Unexpected {
    std::string message;
};

inline Unexpected unexpected(std::string message) {
    return {std::move(message)};
}

template <typename T>
class Expected {
public:
    Expected(T value) : value_(std::in_place_index<0>, std::move(value)) {}
    Expected(Unexpected error) : value_(std::in_place_index<1>, std::move(error.message)) {}

    explicit operator bool() const noexcept { return value_.index() == 0; }
    T& operator*() { return std::get<0>(value_); }
    const T& operator*() const { return std::get<0>(value_); }
    T* operator->() { return &std::get<0>(value_); }
    const T* operator->() const { return &std::get<0>(value_); }
    const std::string& error() const { return std::get<1>(value_); }

private:
    std::variant<T, std::string> value_;
};

} // namespace nav_executor
