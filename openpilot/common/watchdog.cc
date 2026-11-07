#include <string>
#include <unistd.h>

#include "common/watchdog.h"
#include "common/util.h"
#include "common/hardware/hw.h"

// The heartbeat files are named after the pid so the manager can map a file
// back to the process it is watching. The prefix matches common/watchdog.py.
static const std::string watchdog_fn_prefix = Path::shm_path() + "/wd_";

bool watchdog_kick(uint64_t ts) {
  static std::string fn = watchdog_fn_prefix + std::to_string(getpid());
  return util::write_file(fn.c_str(), &ts, sizeof(ts), O_WRONLY | O_CREAT) == 0;
}
