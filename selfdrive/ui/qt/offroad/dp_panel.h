#pragma once

#include "selfdrive/ui/qt/offroad/settings.h"

class DPPanel : public ListWidget {
  Q_OBJECT
public:
  explicit DPPanel(SettingsWindow *parent);

public slots:
  void expandToggleDescription(const QString &param);

private:
  Params params;
  ParamWatcher *fs_watch;
  std::map<std::string, ParamControl*> toggles;
  QString brand;
  bool is_onroad = false;
  bool vehicle_has_long_ctrl;
  bool vehicle_has_radar_unavailable;
  bool device_has_ext_radar_serial = false;

  void add_toyota_toggles();
  void add_vag_toggles();
  void add_mazda_toggles();
  void add_lateral_toggles();
  void add_longitudinal_toggles();
  void add_ui_toggles();
  void add_device_toggles();
  void updateStates();
  void showEvent(QShowEvent *event) override;

  ParamDoubleSpinBoxControl* lca_sec_toggle;
};
