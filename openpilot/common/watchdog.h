#pragma once

#include <cstdint>

// Write a heartbeat for this process so the manager can tell a hung process
// from a busy one. Returns false when the write failed.
bool watchdog_kick(uint64_t ts);
