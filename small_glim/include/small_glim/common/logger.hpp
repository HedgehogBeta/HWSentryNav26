#pragma once

#include <fmt/format.h>
#include <rclcpp/logger.hpp>
#include <rclcpp/logging.hpp>

namespace small_glim::logger {

constexpr const char* LOGGER_NAME = "small_glim";

template<typename... Args>
inline void debug(const char* name, fmt::format_string<Args...> fmt_str, Args&&... args) {
    RCLCPP_DEBUG(
        rclcpp::get_logger(LOGGER_NAME),
        "<%s>: %s", name, fmt::format(fmt_str, std::forward<Args>(args)...).c_str()
    );
}

template<typename... Args>
inline void info(const char* name, fmt::format_string<Args...> fmt_str, Args&&... args) {
    RCLCPP_INFO(
        rclcpp::get_logger(LOGGER_NAME),
        "<%s>: %s", name, fmt::format(fmt_str, std::forward<Args>(args)...).c_str()
    );
}

template<typename... Args>
inline void warn(const char* name, fmt::format_string<Args...> fmt_str, Args&&... args) {
    RCLCPP_WARN(
        rclcpp::get_logger(LOGGER_NAME),
        "<%s>: %s", name, fmt::format(fmt_str, std::forward<Args>(args)...).c_str()
    );
}

template<typename... Args>
inline void error(const char* name, fmt::format_string<Args...> fmt_str, Args&&... args) {
    RCLCPP_ERROR(
        rclcpp::get_logger(LOGGER_NAME),
        "<%s>: %s", name, fmt::format(fmt_str, std::forward<Args>(args)...).c_str()
    );
}

template<typename... Args>
inline void fatal(const char* name, fmt::format_string<Args...> fmt_str, Args&&... args) {
    RCLCPP_FATAL(
        rclcpp::get_logger(LOGGER_NAME),
        "<%s>: %s", name, fmt::format(fmt_str, std::forward<Args>(args)...).c_str()
    );
}

}
