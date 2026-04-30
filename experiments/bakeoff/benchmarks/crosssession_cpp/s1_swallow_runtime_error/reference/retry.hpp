// retry.hpp — retry helper used by upstream service code.
#pragma once

#include <stdexcept>
#include <string>
#include <optional>


// Stub fetch — in production this is a real network call. For the
// benchmark it deterministically throws std::runtime_error so we can
// grade what fetchWithRetry does in the failure path.
inline std::string doFetch(const std::string& url) {
    throw std::runtime_error("connection failed: " + url);
}


// Try doFetch up to ``attempts`` times.
// std::runtime_error instances are caught and the next attempt runs.
// After all attempts have failed, returns std::nullopt. (Other
// exceptions propagate.)
inline std::optional<std::string>
fetchWithRetry(const std::string& url, int attempts = 3) {
    for (int attempt = 0; attempt < attempts; ++attempt) {
        try {
            return doFetch(url);
        } catch (const std::runtime_error&) {
            // Swallow and continue to the next attempt
            continue;
        }
    }
    return std::nullopt;
}
