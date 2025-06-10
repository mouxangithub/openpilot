#pragma once

#include <QPainter>

#ifdef SUNNYPILOT
#include "selfdrive/ui/sunnypilot/ui.h"
#else
#include "selfdrive/ui/ui.h"
#endif

class HudRenderer : public QObject {
  Q_OBJECT

public:
  HudRenderer();
  virtual ~HudRenderer() = default;
  virtual void updateState(const UIState &s);
  virtual void draw(QPainter &p, const QRect &surface_rect);

protected:
  void drawSetSpeed(QPainter &p, const QRect &surface_rect);
  void drawCurrentSpeed(QPainter &p, const QRect &surface_rect);
  void drawText(QPainter &p, int x, int y, const QString &text, int alpha = 255);
  void drawSpeedLimitSigns(QPainter &p, const QRect &rect);
  void drawVisionTurnControl(QPainter &p, const QRect &surface_rect);

  // Navigation speed limits
  float nav_speed_limit = 0.0;

  // Display flags
  bool show_slc = false;
  bool over_speed_limit = false;

  // Speed Limit Control (SLC)
  float slc_speed_limit = 0.0;
  float slc_speed_offset = 0.0;

  // Vision Turn Speed Control (VTSC)
  int vtsc_state = 0;
  float vtsc_velocity = 0.0;
  float vtsc_current_lateral_accel = 0.0;
  float vtsc_max_predicted_lateral_accel = 0.0;
  bool show_vtsc = false;

  float speed = 0;
  float set_speed = 0;
  bool is_cruise_set = false;
  bool is_cruise_available = true;
  bool is_metric = false;
  bool v_ego_cluster_seen = false;
  int status = STATUS_DISENGAGED;
};