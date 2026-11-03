#pragma once

#include <string>

#include "common/params.h"
#include "selfdrive/pandad/panda.h"

void pandad_main_thread(std::string serial, std::string aux_serial);

// deprecated devices
static const std::vector<cereal::PandaState::PandaType> SUPPORTED_PANDA_TYPES = {
  cereal::PandaState::PandaType::DOS,
  cereal::PandaState::PandaType::RED_PANDA,
  cereal::PandaState::PandaType::TRES,
  cereal::PandaState::PandaType::CUATRO,
};


class PandaSafety {
public:
  // config_index: which entry of CarParams.safetyConfigs this panda applies (0 = primary
  // panda, 1 = secondary panda in dual-panda mode).
  PandaSafety(Panda *panda, int config_index = 0) : panda_(panda), config_index_(config_index) {}
  void configureSafetyMode(bool is_onroad);
  bool getOffroadMode();
  bool safetyConfigured() const { return safety_configured_; }

private:
  void updateMultiplexingMode();
  std::vector<std::string> fetchCarParams();
  bool setSafetyMode(const std::vector<std::string> &params_string);

  int config_index_ = 0;
  bool initialized_ = false;
  bool log_once_ = false;
  bool safety_configured_ = false;
  bool prev_obd_multiplexing_ = false;
  Panda *panda_;
  Params params_;
};
