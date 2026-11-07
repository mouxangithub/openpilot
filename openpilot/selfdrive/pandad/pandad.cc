#include "selfdrive/pandad/pandad.h"

#include <array>
#include <atomic>
#include <bitset>
#include <cassert>
#include <cerrno>
#include <memory>
#include <thread>
#include <utility>

#include "openpilot/cereal/gen/cpp/car.capnp.h"
#include "openpilot/cereal/messaging/messaging.h"
#include "openpilot/cereal/services.h"
#include "common/ratekeeper.h"
#include "common/swaglog.h"
#include "common/timing.h"
#include "common/util.h"
#include "common/hardware/hw.h"

#define MAX_IR_PANDA_VAL 50
#define CUTOFF_IL 400
#define SATURATE_IL 1000

ExitHandler do_exit;

// dual-panda mode: while the secondary (aux) panda is still in the ELM327
// fingerprinting phase, its send thread mirrors the primary panda's buses 0-2
// so UDS/fw queries reach powertrain ECUs that are only wired to the aux;
// once safety is configured it switches to segment routing (buses 4-6).
std::atomic<bool> aux_elm327_mirror{false};

bool check_connected(Panda *panda) {
  if (!panda->connected()) {
    do_exit = true;
    return false;
  }
  return true;
}

bool process_mads_heartbeat(SubMaster *sm) {
  const auto &mads = (*sm)["selfdriveStateSP"].getSelfdriveStateSP().getMads();
  return sm->allAliveAndValid({"selfdriveStateSP"}) && mads.getEnabled();
}

Panda *connect(std::string serial) {
  std::unique_ptr<Panda> panda;
  try {
    panda = std::make_unique<Panda>(serial);
  } catch (std::exception &e) {
    return nullptr;
  }

  // common panda config
  if (getenv("BOARDD_LOOPBACK")) {
    panda->set_loopback(true);
  }

  for (int i = 0; i < PANDA_CAN_CNT; i++) {
    panda->set_can_fd_auto(i, true);
  }

  bool is_supported_panda = std::find(SUPPORTED_PANDA_TYPES.begin(), SUPPORTED_PANDA_TYPES.end(), panda->hw_type) != SUPPORTED_PANDA_TYPES.end();

  if (!is_supported_panda) {
    LOGW("panda %s is not supported (hw_type: %i), skipping firmware check...", panda->hw_serial().c_str(), static_cast<uint16_t>(panda->hw_type));
    return panda.release();
  }

  if (!panda->up_to_date() && !getenv("BOARDD_SKIP_FW_CHECK")) {
    throw std::runtime_error("Panda firmware out of date. Run pandad.py to update.");
  }

  return panda.release();
}

void can_send_thread(Panda *panda, Panda *aux_panda, bool dual_can, bool fake_send) {
  util::set_thread_name("pandad_can_send");

  AlignedBuffer aligned_buf;
  std::unique_ptr<SubSocket> subscriber(SubSocket::create("sendcan", false, services.at("sendcan").queue_size));
  assert(subscriber != NULL);
  subscriber->setTimeout(100);

  // run as fast as messages come in
  while (!do_exit && check_connected(panda)) {
    std::unique_ptr<Message> msg(subscriber->receive());
    if (!msg) {
      continue;
    }

    capnp::FlatArrayMessageReader cmsg(aligned_buf.align(msg.get()));
    cereal::Event::Reader event = cmsg.getRoot<cereal::Event>();

    // Don't send if older than 1 second
    if ((nanos_since_boot() - event.getLogMonoTime() < 1e9) && !fake_send) {
      LOGD("sending sendcan to panda: %s", (panda->hw_serial()).c_str());
      // primary panda: buses 0-2 (frames with src >= PANDA_BUS_OFFSET are skipped)
      panda->can_send(event.getSendcan());

      // secondary panda in dual mode: either mirror the primary's buses 0-2
      // during fingerprinting, or serve its own bus block 4-6 (sent with the
      // offset subtracted, i.e. the panda's local bus numbering)
      if (dual_can && aux_panda != nullptr && aux_panda->connected()) {
        if (aux_elm327_mirror) {
          aux_panda->can_send(event.getSendcan());
        } else {
          aux_panda->can_send(event.getSendcan(), PANDA_BUS_OFFSET);
        }
      }
      LOGD("sendcan sent to panda: %s", (panda->hw_serial()).c_str());
    } else {
      LOGE("sendcan too old to send: %" PRIu64 ", %" PRIu64, nanos_since_boot(), event.getLogMonoTime());
    }
  }
}

void can_recv(Panda *panda, PubMaster *pm, uint8_t src_offset = 0U) {
  std::vector<can_frame> raw_can_data;
  {
    bool comms_healthy = panda->can_receive(raw_can_data);

    MessageBuilder msg;
    auto evt = msg.initEvent();
    evt.setValid(comms_healthy);
    auto canData = evt.initCan(raw_can_data.size());
    for (size_t i = 0; i < raw_can_data.size(); ++i) {
      canData[i].setAddress(raw_can_data[i].address);
      canData[i].setDat(kj::arrayPtr((uint8_t*)raw_can_data[i].dat.data(), raw_can_data[i].dat.size()));
      // logical bus: the secondary panda's local buses are offset by
      // PANDA_BUS_OFFSET (rejected/returned markers 128/192 pass through)
      uint8_t src = (uint8_t)raw_can_data[i].src;
      if (src < PANDA_BUS_OFFSET) {
        src += src_offset;
      }
      canData[i].setSrc(src);
    }
    pm->send("can", msg);
  }
}

// receive thread for the secondary (aux) CAN panda in dual-panda mode; unlike
// the primary, a disconnect here must not bring the whole daemon down.
// During the fingerprinting mirror phase its frames are published with the
// local bus numbers as-is (0-2) so UDS responses match the bus the queries
// were sent on; after safety is configured they are offset to 4-6.
void can_recv_thread_aux(Panda *panda, PubMaster *pm) {
  util::set_thread_name("pandad_can_recv_aux");
  while (!do_exit) {
    if (!panda->connected() || !panda->comms_healthy()) {
      LOGE("aux CAN panda disconnected, aux receive thread exiting");
      return;
    }
    can_recv(panda, pm, aux_elm327_mirror ? 0U : (uint8_t)PANDA_BUS_OFFSET);
  }
}

void fill_panda_state(cereal::PandaState::Builder &ps, cereal::PandaState::PandaType hw_type, const health_t &health) {
  ps.setVoltage(health.voltage_pkt);
  ps.setCurrent(health.current_pkt);
  ps.setUptime(health.uptime_pkt);
  ps.setSafetyTxBlocked(health.safety_tx_blocked_pkt);
  ps.setSafetyRxInvalid(health.safety_rx_invalid_pkt);
  ps.setIgnitionLine((health.flags_pkt & HEALTH_FLAG_IGNITION_LINE) != 0U);
  ps.setIgnitionCan((health.flags_pkt & HEALTH_FLAG_IGNITION_CAN) != 0U);
  ps.setControlsAllowed((health.flags_pkt & HEALTH_FLAG_CONTROLS_ALLOWED) != 0U);
  ps.setTxBufferOverflow(health.tx_buffer_overflow_pkt);
  ps.setRxBufferOverflow(health.rx_buffer_overflow_pkt);
  ps.setPandaType(hw_type);
  ps.setSafetyModel(cereal::CarParams::SafetyModel(health.safety_mode_pkt));
  ps.setSafetyParam(health.safety_param_pkt);
  ps.setFaultStatus(cereal::PandaState::FaultStatus(health.fault_status_pkt));
  ps.setPowerSaveEnabled((health.flags_pkt & HEALTH_FLAG_POWER_SAVE_ENABLED) != 0U);
  ps.setHeartbeatLost((health.flags_pkt & HEALTH_FLAG_HEARTBEAT_LOST) != 0U);
  ps.setAlternativeExperience(health.alternative_experience_pkt);
  ps.setHarnessStatus(cereal::PandaState::HarnessStatus(health.car_harness_status_pkt));
  ps.setInterruptLoad(health.interrupt_load_pkt / 255.0f);
  ps.setFanPower(health.fan_power);
  ps.setSafetyRxChecksInvalid((health.flags_pkt & HEALTH_FLAG_SAFETY_RX_CHECKS_INVALID) != 0U);
  ps.setNmiReset((health.flags_pkt & HEALTH_FLAG_NMI_RESET) != 0U);
  ps.setHardfaultReset((health.flags_pkt & HEALTH_FLAG_HARDFAULT_RESET) != 0U);
  ps.setSpiErrorCount(health.spi_error_count_pkt);
  ps.setSbu1Voltage(health.sbu1_voltage_mV / 1000.0f);
  ps.setSbu2Voltage(health.sbu2_voltage_mV / 1000.0f);
  ps.setSoundOutputLevel(health.sound_output_level_pkt);
  ps.setControlsAllowedLateral(health.controls_allowed_sp_pkt & 1);
  ps.setControlsAllowedLongitudinal((health.controls_allowed_sp_pkt >> 1) & 1);
}

void fill_panda_can_state(cereal::PandaState::PandaCanState::Builder &cs, const can_health_t &can_health) {
  cs.setBusOff((bool)can_health.bus_off);
  cs.setBusOffCnt(can_health.bus_off_cnt);
  cs.setErrorWarning((bool)can_health.error_warning);
  cs.setErrorPassive((bool)can_health.error_passive);
  cs.setLastError(cereal::PandaState::PandaCanState::LecErrorCode(can_health.last_error));
  cs.setLastStoredError(cereal::PandaState::PandaCanState::LecErrorCode(can_health.last_stored_error));
  cs.setLastDataError(cereal::PandaState::PandaCanState::LecErrorCode(can_health.last_data_error));
  cs.setLastDataStoredError(cereal::PandaState::PandaCanState::LecErrorCode(can_health.last_data_stored_error));
  cs.setReceiveErrorCnt(can_health.receive_error_cnt);
  cs.setTransmitErrorCnt(can_health.transmit_error_cnt);
  cs.setTotalErrorCnt(can_health.total_error_cnt);
  cs.setTotalTxLostCnt(can_health.total_tx_lost_cnt);
  cs.setTotalRxLostCnt(can_health.total_rx_lost_cnt);
  cs.setTotalTxCnt(can_health.total_tx_cnt);
  cs.setTotalRxCnt(can_health.total_rx_cnt);
  cs.setTotalFwdCnt(can_health.total_fwd_cnt);
  cs.setCanSpeed(can_health.can_speed);
  cs.setCanDataSpeed(can_health.can_data_speed);
  cs.setCanfdEnabled(can_health.canfd_enabled);
  cs.setBrsEnabled(can_health.brs_enabled);
  cs.setCanfdNonIso(can_health.canfd_non_iso);
  cs.setIrq0CallRate(can_health.irq0_call_rate);
  cs.setIrq1CallRate(can_health.irq1_call_rate);
  cs.setIrq2CallRate(can_health.irq2_call_rate);
  cs.setCanCoreResetCnt(can_health.can_core_reset_cnt);
}

std::optional<bool> send_panda_states(PubMaster *pm, Panda *panda, Panda *aux_panda, bool dual_can, bool is_onroad, bool spoofing_started, bool always_offroad) {
  // build msg
  MessageBuilder msg;
  auto evt = msg.initEvent();
  const int num_states = (dual_can && aux_panda != nullptr && aux_panda->connected()) ? 2 : 1;
  auto pss = evt.initPandaStates(num_states);

  std::optional<bool> ignition;
  for (int i = 0; i < num_states; i++) {
    Panda *p = (i == 0) ? panda : aux_panda;

    auto health_opt = p->get_state();
    if (!health_opt) {
      return std::nullopt;
    }

    health_t health = *health_opt;

    std::array<can_health_t, PANDA_CAN_CNT> can_health{};
    for (uint32_t k = 0; k < PANDA_CAN_CNT; k++) {
      auto can_health_opt = p->get_can_state(k);
      if (!can_health_opt) {
        return std::nullopt;
      }
      can_health[k] = *can_health_opt;
    }

    if (spoofing_started) {
      health.flags_pkt |= HEALTH_FLAG_IGNITION_LINE;
    }

    // on comma three setups with an external Red Panda, the dos can get false
    // positive ignitions due to the harness box without a harness connector, so
    // ignore its ignition line (ported from master-c3's red_panda_comma_three;
    // pandad.py exports PANDAD_MASK_DOS_IGNITION when it sees a Red Panda
    // alongside the internal dos)
    static const bool mask_dos_ignition = getenv("PANDAD_MASK_DOS_IGNITION") != nullptr;
    if (mask_dos_ignition && (p->hw_type == cereal::PandaState::PandaType::DOS)) {
      health.flags_pkt &= ~HEALTH_FLAG_IGNITION_LINE;
    }

    bool ignition_local = ((health.flags_pkt & (HEALTH_FLAG_IGNITION_LINE | HEALTH_FLAG_IGNITION_CAN)) != 0U) && !always_offroad;

    // Make sure CAN buses are live: safety_setter_thread does not work if Panda CAN are silent and there is only one other CAN node
    if (health.safety_mode_pkt == (uint8_t)(cereal::CarParams::SafetyModel::SILENT)) {
      p->set_safety_model(cereal::CarParams::SafetyModel::NO_OUTPUT);
    }

    bool power_save_desired = !ignition_local;
    if (((health.flags_pkt & HEALTH_FLAG_POWER_SAVE_ENABLED) != 0U) != power_save_desired) {
      p->set_power_saving(power_save_desired);
    }

    // set safety mode to NO_OUTPUT when car is off or we're not onroad. ELM327 is an alternative if we want to leverage athenad/connect
    bool should_close_relay = !ignition_local || !is_onroad;
    if (should_close_relay && (health.safety_mode_pkt != (uint8_t)(cereal::CarParams::SafetyModel::NO_OUTPUT))) {
      p->set_safety_model(cereal::CarParams::SafetyModel::NO_OUTPUT);
    }

    if (i == 0) {
      if (!p->comms_healthy()) {
        evt.setValid(false);
      }
      ignition = ignition_local;
    }

    auto ps = pss[i];
    fill_panda_state(ps, p->hw_type, health);

    auto cs = std::array{ps.initCanState0(), ps.initCanState1(), ps.initCanState2()};
    for (uint32_t j = 0; j < PANDA_CAN_CNT; j++) {
      fill_panda_can_state(cs[j], can_health[j]);
    }

    // Convert faults bitset to capnp list
    // bits above the last fault type would leave unset entries, which read as relayMalfunction
    std::bitset<sizeof(health.faults_pkt) * 8> fault_bits(health.faults_pkt & ((2U << size_t(cereal::PandaState::FaultType::TIMER)) - 1U));
    auto faults = ps.initFaults(fault_bits.count());

    size_t j = 0;
    for (size_t f = size_t(cereal::PandaState::FaultType::RELAY_MALFUNCTION);
         f <= size_t(cereal::PandaState::FaultType::TIMER); f++) {
      if (fault_bits.test(f)) {
        faults.set(j, cereal::PandaState::FaultType(f));
        j++;
      }
    }
  }

  pm->send("pandaStates", msg);
  return ignition;
}

void send_peripheral_state(Panda *panda, PubMaster *pm) {
  auto health_opt = panda->get_state();
  if (!health_opt) {
    return;
  }

  // build msg
  MessageBuilder msg;
  auto evt = msg.initEvent();
  evt.setValid(panda->comms_healthy());

  auto ps = evt.initPeripheralState();
  ps.setPandaType(panda->hw_type);

  health_t health = *health_opt;
  ps.setVoltage(health.voltage_pkt);
  ps.setCurrent(health.current_pkt);

  uint16_t fan_speed_rpm = panda->get_fan_speed();
  ps.setFanSpeedRpm(fan_speed_rpm);

  pm->send("peripheralState", msg);
}

void process_panda_state(Panda *panda, Panda *peripheral_panda, PubMaster *pm, bool engaged, bool engaged_mads, bool is_onroad, bool spoofing_started, bool always_offroad, bool dual_can) {
  auto ignition_opt = send_panda_states(pm, panda, peripheral_panda, dual_can, is_onroad, spoofing_started, always_offroad);
  if (!ignition_opt) {
    LOGE("Failed to get ignition_opt");
    return;
  }

  // check if we should have pandad reconnect
  if (!ignition_opt.value()) {
    if (!panda->comms_healthy()) {
      LOGE("Reconnecting, communication to panda not healthy");
      do_exit = true;
    }
  }

  panda->send_heartbeat(engaged, engaged_mads);

  // keep the aux (peripheral) panda's heartbeat fed so its firmware never
  // flags heartbeat_lost; it does not do CAN safety, it only drives the fan
  if (peripheral_panda != nullptr && peripheral_panda != panda && peripheral_panda->connected()) {
    peripheral_panda->send_heartbeat(engaged, engaged_mads);
  }
}

void process_peripheral_state(Panda *panda, PubMaster *pm, bool no_fan_control, bool is_onroad) {
  static Params params;
  static SubMaster sm({"deviceState", "cabinCameraState"});

  static uint64_t last_cabin_camera_t = 0;
  static uint16_t prev_fan_speed = 999;
  static int ir_pwr = 0;
  static int prev_ir_pwr = 999;
  static uint32_t prev_frame_id = UINT32_MAX;
  static bool driver_view = false;
  static bool not_car = false;
  static bool not_car_checked = false;

  // TODO: can we merge these?
  static FirstOrderFilter integ_lines_filter(0, 30.0, 0.05);
  static FirstOrderFilter integ_lines_filter_driver_view(0, 5.0, 0.05);

  {
    sm.update(0);
    if (sm.updated("deviceState") && !no_fan_control) {
      // Fan speed
      uint16_t fan_speed = sm["deviceState"].getDeviceState().getFanSpeedPercentDesired();
      if (fan_speed != prev_fan_speed || sm.frame % 100 == 0) {
        panda->set_fan_speed(fan_speed);
        prev_fan_speed = fan_speed;
      }
    }

    if (sm.updated("cabinCameraState")) {
      auto event = sm["cabinCameraState"];
      int cur_integ_lines = event.getCabinCameraState().getIntegLines();

      // reset the filter when camerad restarts
      if (event.getCabinCameraState().getFrameId() < prev_frame_id) {
        integ_lines_filter.reset(0);
        integ_lines_filter_driver_view.reset(0);
        driver_view = params.getBool("IsDriverViewEnabled");
      }
      prev_frame_id = event.getCabinCameraState().getFrameId();

      cur_integ_lines = (driver_view ? integ_lines_filter_driver_view : integ_lines_filter).update(cur_integ_lines);
      last_cabin_camera_t = event.getLogMonoTime();

      if (cur_integ_lines <= CUTOFF_IL) {
        ir_pwr = 0;
      } else if (cur_integ_lines > SATURATE_IL) {
        ir_pwr = 100;
      } else {
        ir_pwr = 100 * (cur_integ_lines - CUTOFF_IL) / (SATURATE_IL - CUTOFF_IL);
      }
    }

    // Disable IR on input timeout or when requested offroad.
    if (nanos_since_boot() - last_cabin_camera_t > 1e9 || (!is_onroad && params.getBool("DisableDriverCameraIR"))) {
      ir_pwr = 0;
    }

    // turn off IR leds if body
    if (!not_car_checked && is_onroad) {
      std::string cp_bytes = params.get("CarParams");
      if (cp_bytes.size() > 0) {
        AlignedBuffer aligned_buf;
        capnp::FlatArrayMessageReader cmsg(aligned_buf.align(cp_bytes.data(), cp_bytes.size()));
        cereal::CarParams::Reader CP = cmsg.getRoot<cereal::CarParams>();
        not_car = CP.getNotCar();
        not_car_checked = true;
      }
    }
    if (not_car) {
      ir_pwr = 0;
    }

    if (ir_pwr != prev_ir_pwr || sm.frame % 100 == 0) {
      int16_t ir_panda = util::map_val(ir_pwr, 0, 100, 0, MAX_IR_PANDA_VAL);
      panda->set_ir_pwr(ir_panda);
      Hardware::set_ir_power(ir_pwr);
      prev_ir_pwr = ir_pwr;
    }
  }
}

void pandad_run(Panda *panda, Panda *peripheral_panda, bool dual_can) {
  const bool no_fan_control = getenv("NO_FAN_CONTROL") != nullptr;
  const bool spoofing_started = getenv("STARTED") != nullptr;
  const bool fake_send = getenv("FAKESEND") != nullptr;

  Panda *aux_can_panda = (dual_can && peripheral_panda != nullptr && peripheral_panda != panda) ? peripheral_panda : nullptr;

  // dual-panda: the secondary CAN panda starts in the fingerprinting mirror
  // phase; it flips to segment routing (buses 4-6) once its safety is configured
  if (aux_can_panda != nullptr) {
    aux_elm327_mirror = true;
  }

  // Start helper thread for event-driven sendcan.
  RateKeeper rk("pandad", 100);
  SubMaster sm({"selfdriveState", "deviceState", "selfdriveStateSP"});
  PubMaster pm({"can", "pandaStates", "peripheralState"});
  std::thread send_thread(can_send_thread, panda, aux_can_panda, dual_can, fake_send);

  // secondary CAN panda receive thread (publishes buses 4-6)
  std::thread aux_recv_thread;
  if (aux_can_panda != nullptr) {
    aux_recv_thread = std::thread(can_recv_thread_aux, aux_can_panda, &pm);
  }

  PandaSafety panda_safety(panda);
  std::unique_ptr<PandaSafety> aux_safety;
  if (aux_can_panda != nullptr) {
    aux_safety = std::make_unique<PandaSafety>(aux_can_panda, 1);
  }
  bool engaged = false;
  bool engaged_mads = false;
  bool is_onroad = false;
  bool always_offroad = false;

  // Main loop: receive CAN first, then process lower priority panda and peripheral state.
  while (!do_exit && check_connected(panda)) {
    can_recv(panda, &pm);

    // Process peripheral state at 20 Hz
    if (rk.frame() % 5 == 0) {
      process_peripheral_state(peripheral_panda, &pm, no_fan_control, is_onroad);
    }

    // Process panda state at 10 Hz
    if (rk.frame() % 10 == 0) {
      sm.update(0);
      engaged = sm.allAliveAndValid({"selfdriveState"}) && sm["selfdriveState"].getSelfdriveState().getEnabled();
      if (sm.updated("deviceState")) {
        is_onroad = sm["deviceState"].getDeviceState().getStarted();
      }
      engaged_mads = process_mads_heartbeat(&sm);
      always_offroad = panda_safety.getOffroadMode();
      process_panda_state(panda, peripheral_panda, &pm, engaged, engaged_mads, is_onroad, spoofing_started, always_offroad, dual_can);
      panda_safety.configureSafetyMode(is_onroad);
      if (aux_safety) {
        aux_safety->configureSafetyMode(is_onroad);
        // mirror while the aux is still in the ELM327/fingerprinting phase
        aux_elm327_mirror = !aux_safety->safetyConfigured();
      }
    }

    // Send out peripheralState at 2Hz
    if (rk.frame() % 50 == 0) {
      send_peripheral_state(peripheral_panda, &pm);
    }

    // Forward logs from panda to cloudlog if available
    std::string log = panda->serial_read();
    if (!log.empty()) {
      if (log.find("Register 0x") != std::string::npos) {
        // Log register divergent faults as errors
        LOGE("%s", log.c_str());
      } else {
        LOGD("%s", log.c_str());
      }
    }

    rk.keepTime();
  }

  // Close relay on exit to prevent a fault
  if (is_onroad && !engaged) {
    if (panda->connected()) {
      panda->set_safety_model(cereal::CarParams::SafetyModel::NO_OUTPUT);
    }
    if (aux_can_panda != nullptr && aux_can_panda->connected()) {
      aux_can_panda->set_safety_model(cereal::CarParams::SafetyModel::NO_OUTPUT);
    }
  }

  do_exit = true;
  send_thread.join();
  if (aux_recv_thread.joinable()) {
    aux_recv_thread.join();
  }
}

void pandad_main_thread(std::string serial, std::string aux_serial) {
  if (serial.empty()) {
    auto serials = Panda::list();

    if (serials.empty()) {
      LOGW("no pandas found, exiting");
      return;
    }
    serial = serials[0];
  }

  LOGW("connecting to panda: %s", serial.c_str());

  Panda *panda = nullptr;
  while (!do_exit) {
    panda = connect(serial);
    if (panda) break;
    util::sleep_for(100);
  }

  // aux (peripheral) panda: when the active CAN panda is an external device
  // (e.g. Red Panda on the harness with UseRedPanda), the internal dos is
  // connected here so it keeps fan/peripheral control - master-c3 achieves
  // the same by sorting the internal panda first and using it as
  // peripheral_panda. Non-fatal: without it the fan falls back to the
  // firmware's own thermal default.
  Panda *aux_panda = nullptr;
  bool dual_can = false;
  if (!aux_serial.empty() && aux_serial != serial) {
    try {
      aux_panda = connect(aux_serial);
    } catch (std::exception &e) {
      aux_panda = nullptr;
    }
    if (aux_panda) {
      // Dual-panda CAN mode (DualPanda param): the aux (internal dos, wired to
      // the OBD/powertrain segment) becomes a secondary CAN panda serving
      // logical buses 4-6, while the active panda (e.g. external Red Panda on
      // the camera segment) keeps buses 0-2. safetyConfigs[1] applies to it.
      // Without the param, the aux is forced silent: a panda nobody configures
      // does not come up silent - it keeps whatever state it was last left in -
      // typically the elm327 passthrough from fingerprinting, which bridges
      // every CAN channel it has. Its spare channels are unwired, so frames
      // sent there never see an ACK and the controller retries them forever,
      // flooding the vehicle bus with errors until a camera ECU cries fault.
      static Params params;
      dual_can = params.getBool("DualPanda");
      if (dual_can) {
        LOGW("connected aux CAN panda: %s (dual-panda mode, buses 4-6)", aux_serial.c_str());
      } else {
        aux_panda->set_safety_model(cereal::CarParams::SafetyModel::NO_OUTPUT);
        LOGW("connected aux peripheral panda: %s (safety forced to NO_OUTPUT)", aux_serial.c_str());
      }
    } else {
      LOGW("failed to connect aux peripheral panda %s, fan control unavailable", aux_serial.c_str());
    }
  }

  if (!do_exit) {
    LOGW("connected to panda");
    pandad_run(panda, aux_panda ? aux_panda : panda, dual_can);
  }

  delete panda;
  delete aux_panda;
}
