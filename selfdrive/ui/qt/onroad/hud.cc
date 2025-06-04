#include "selfdrive/ui/qt/onroad/hud.h"

#include <cmath>
#include <QPainterPath>

#include "selfdrive/ui/qt/util.h"

constexpr int SET_SPEED_NA = 255;
static QColor interpColor(float x, const std::vector<float> &x_vals, const std::vector<QColor> &colors) {
  assert(x_vals.size() == colors.size() && x_vals.size() >= 2);
  for (size_t i = 1; i < x_vals.size(); ++i) {
    if (x < x_vals[i]) {
      float t = (x - x_vals[i - 1]) / (x_vals[i] - x_vals[i - 1]);
      QColor c1 = colors[i - 1];
      QColor c2 = colors[i];
      return QColor::fromRgbF(
        c1.redF() + (c2.redF() - c1.redF()) * t,
        c1.greenF() + (c2.greenF() - c1.greenF()) * t,
        c1.blueF() + (c2.blueF() - c1.blueF()) * t,
        c1.alphaF() + (c2.alphaF() - c1.alphaF()) * t
      );
    }
  }
  return colors.back();  // Default to last color if out of range
}

HudRenderer::HudRenderer() {
  // Load images for turn signs
  left_img = loadPixmap("../assets/img_turn_left", {64, 64});
  right_img = loadPixmap("../assets/img_turn_right", {64, 64});
  map_img = loadPixmap("../assets/img_map", {32, 32});

  // VTC colors for different states
  //tcs_colors = {
  //  QColor(0, 0, 0, 50),           // DISABLED
  //  QColor(255, 255, 255, 200),    // ENABLED
   // QColor(255, 255, 0, 255),      // ACTIVE
  //  QColor(255, 0, 0, 255)         // BRAKING
  //};
}

void HudRenderer::updateState(const UIState &s) {
  is_metric = s.scene.is_metric;
  status = s.status;

  const SubMaster &sm = *(s.sm);
  if (sm.rcv_frame("carState") < s.scene.started_frame) {
    is_cruise_set = false;
    set_speed = SET_SPEED_NA;
    speed = 0.0;
    return;
  }

  const auto &controls_state = sm["controlsState"].getControlsState();
  const auto &car_state = sm["carState"].getCarState();

  // Navigation and longitudinal plan data
  const bool nav_alive = sm.alive("navInstruction") && sm["navInstruction"].getValid();
  const auto nav_instruction = nav_alive ? sm["navInstruction"].getNavInstruction() : cereal::NavInstruction::Reader();
  const auto lp_sp = sm["longitudinalPlanSP"].getLongitudinalPlanSP();
  //const auto slc = lp_sp.getSlc();

  // Speed limit from navigation (force for testing)
  if (nav_alive) {
    nav_speed_limit = nav_instruction.getSpeedLimit() * (is_metric ? MS_TO_KPH : MS_TO_MPH);
    auto speed_limit_sign = nav_instruction.getSpeedLimitSign();
    has_us_speed_limit = (speed_limit_sign == cereal::NavInstruction::SpeedLimitSign::MUTCD);
    has_eu_speed_limit = (speed_limit_sign == cereal::NavInstruction::SpeedLimitSign::VIENNA);
  } else {
    // Force test values when no navigation data
    nav_speed_limit = is_metric ? 80.0 : 55.0;  // 80 km/h or 55 mph
    has_us_speed_limit = !is_metric;
    has_eu_speed_limit = is_metric;
  }

  // Longitudinal plan data (if available)
  if (sm.alive("longitudinalPlanSP")) {
	const auto slc = lp_sp.getSlc();
    // Speed Limit Control
    slc_state = static_cast<int>(slc.getState());
    slc_speed_limit = slc.getSpeedLimit() * (is_metric ? MS_TO_KPH : MS_TO_MPH);
    slc_speed_offset = slc.getSpeedLimitOffset() * (is_metric ? MS_TO_KPH : MS_TO_MPH);
    slc_distance = int(slc.getDistToSpeedLimit() * (is_metric ? MS_TO_KPH : MS_TO_MPH) / 10.0) * 10;

    //is_map_speed_limit = slc.getIsMapSpeedLimit();

    // Vision Turn Controller
    //vtc_speed = lp_sp.getVisionTurnSpeed() * (is_metric ? MS_TO_KPH : MS_TO_MPH);
    //vtc_state = lp_sp.getVisionTurnControllerState();

    // Turn Speed Controller
    //turn_speed = lp_sp.getTurnSpeed() * (is_metric ? MS_TO_KPH : MS_TO_MPH);
    //turn_distance = int(lp_sp.getDistToTurn() * (is_metric ? MS_TO_KPH : MS_TO_MPH) / 10.0) * 10;
    //turn_state = lp_sp.getTurnSpeedControlState();
    //turn_sign = lp_sp.getTurnSign();

    // Determine what to show (force SLC for testing)
    show_slc = slc_speed_limit > 0.0 || true;  // Force show SLC

    // Force some SLC values for testing if not available
    if (slc_speed_limit <= 0.0) {
      slc_speed_limit = is_metric ? 70.0 : 45.0;  // 70 km/h or 45 mph
      slc_state = static_cast<int>(cereal::LongitudinalPlanSP::SpeedLimitControlState::ACTIVE);
      slc_speed_offset = is_metric ? 5.0 : 3.0;   // +5 km/h or +3 mph offset
      slc_distance = is_metric ? 500 : 1640;      // 500m or 1640ft (500m)
    }
    //show_vtc = vtc_state > cereal::LongitudinalPlanSP::VisionTurnControllerState::DISABLED;
    //show_turn_speed = turn_speed > 0.0 && std::round(turn_speed) < 224 &&
    //                 (turn_speed < speed || s.scene.show_debug_ui);
  } else {
    show_slc = false;
    //show_vtc = false;
    //show_turn_speed = false;
  }

  // Handle older routes where vCruiseCluster is not set
  set_speed = car_state.getVCruiseCluster() == 0.0 ? controls_state.getVCruiseDEPRECATED() : car_state.getVCruiseCluster();
  is_cruise_set = set_speed > 0 && set_speed != SET_SPEED_NA;
  is_cruise_available = set_speed != -1;

  if (is_cruise_set && !is_metric) {
    set_speed *= KM_TO_MILE;
  }

  // Handle older routes where vEgoCluster is not set
  v_ego_cluster_seen = v_ego_cluster_seen || car_state.getVEgoCluster() != 0.0;
  float v_ego = v_ego_cluster_seen ? car_state.getVEgoCluster() : car_state.getVEgo();
  speed = std::max<float>(0.0f, v_ego * (is_metric ? MS_TO_KPH : MS_TO_MPH));

  // Check if over speed limit
  over_speed_limit = (show_slc && slc_speed_limit > 0) ?
                    (speed > slc_speed_limit + slc_speed_offset + 5.0) :
                    (nav_speed_limit > 0 && speed > nav_speed_limit + 5.0);
}

void HudRenderer::draw(QPainter &p, const QRect &surface_rect) {
  p.save();

  // Draw header gradient
  QLinearGradient bg(0, UI_HEADER_HEIGHT - (UI_HEADER_HEIGHT / 2.5), 0, UI_HEADER_HEIGHT);
  bg.setColorAt(0, QColor::fromRgbF(0, 0, 0, 0.45));
  bg.setColorAt(1, QColor::fromRgbF(0, 0, 0, 0));
  p.fillRect(0, 0, surface_rect.width(), UI_HEADER_HEIGHT, bg);

  if (is_cruise_available) {
    drawSetSpeed(p, surface_rect);
  }

  // Draw speed limit signs (force always show for testing)
  if (show_slc || nav_speed_limit > 0 || true) {  // Force always draw
    drawSpeedLimitSigns(p, surface_rect);
  }

  drawCurrentSpeed(p, surface_rect);

  // Draw additional controls on the right side
  //if (show_vtc) {
  //  drawVisionTurnController(p, surface_rect);
  //}

  //if (show_turn_speed) {
  //  drawTurnSpeedController(p, surface_rect);
  //}

  p.restore();
}

void HudRenderer::drawSetSpeed(QPainter &p, const QRect &surface_rect) {
  // Calculate size adjustments for speed limit signs
  const int sign_margin = 12;
  const int us_sign_height = 186;
  const int eu_sign_size = 176;

  const QSize default_size = {172, 204};
  QSize set_speed_size = is_metric ? QSize(200, 204) : default_size;

  // Adjust size if we have speed limit signs to show
  bool has_nav_sign = (has_us_speed_limit || has_eu_speed_limit) && nav_speed_limit > 0;
  bool has_slc_sign = show_slc && is_map_speed_limit;

  if (has_nav_sign || has_slc_sign) {
    if (!is_metric || has_us_speed_limit) {
      set_speed_size.rheight() += us_sign_height + sign_margin;
    } else if (is_metric || has_eu_speed_limit) {
      set_speed_size.rheight() += eu_sign_size + sign_margin;
    }
  }

  QRect set_speed_rect(QPoint(60 + (default_size.width() - set_speed_size.width()) / 2, 45), set_speed_size);

  // Draw set speed box with appropriate corner radius
  int bottom_radius = ((is_metric && (has_slc_sign || has_eu_speed_limit)) || has_eu_speed_limit) ? 100 : 32;
  p.setPen(QPen(QColor(255, 255, 255, 75), 6));
  p.setBrush(QColor(0, 0, 0, 166));
  p.drawRoundedRect(set_speed_rect, bottom_radius, bottom_radius);


  // Colors based on status and speed limit comparison
  QColor max_color = QColor(0xa6, 0xa6, 0xa6, 0xff);
  QColor set_speed_color = QColor(0x72, 0x72, 0x72, 0xff);

  if (is_cruise_set) {
    set_speed_color = QColor(255, 255, 255);
    if (status == STATUS_DISENGAGED) {
      max_color = QColor(255, 255, 255);
    } else if (status == STATUS_OVERRIDE) {
      max_color = QColor(0x91, 0x9b, 0x95, 0xff);
    } else {
      max_color = QColor(0x80, 0xd8, 0xa6, 0xff);

      // Color interpolation based on speed limit comparison
      float comparison_speed = show_slc ? slc_speed_limit : nav_speed_limit;
      if (comparison_speed > 0) {
        auto interp_color = [=](QColor c1, QColor c2, QColor c3) {
          return interpColor(set_speed, {comparison_speed + 5, comparison_speed + 15, comparison_speed + 25}, {c1, c2, c3});
        };
        max_color = interp_color(max_color, QColor(0xff, 0xe4, 0xbf), QColor(0xff, 0xbf, 0xbf));
        set_speed_color = interp_color(set_speed_color, QColor(0xff, 0x95, 0x00), QColor(0xff, 0x00, 0x00));
      }
    }
  }

  // Draw "MAX" text
  p.setFont(InterFont(40, QFont::DemiBold));
  p.setPen(max_color);
  p.drawText(set_speed_rect.adjusted(0, 27, 0, 0), Qt::AlignTop | Qt::AlignHCenter, tr("MAX"));

  // Draw set speed
  QString setSpeedStr = is_cruise_set ? QString::number(std::nearbyint(set_speed)) : "–";
  p.setFont(InterFont(90, QFont::Bold));
  p.setPen(set_speed_color);
  p.drawText(set_speed_rect.adjusted(0, 77, 0, 0), Qt::AlignTop | Qt::AlignHCenter, setSpeedStr);
}

void HudRenderer::drawSpeedLimitSigns(QPainter &p, const QRect &surface_rect) {
  const int sign_margin = 12;
  const QSize default_size = {172, 204};
  QSize set_speed_size = is_metric ? QSize(200, 204) : default_size;
  QRect set_speed_rect(QPoint(60 + (default_size.width() - set_speed_size.width()) / 2, 45), set_speed_size);

  QRect sign_rect = set_speed_rect.adjusted(sign_margin, default_size.height(), -sign_margin, -sign_margin);

  // Determine which speed limit to show and its properties
  float display_speed = show_slc ? slc_speed_limit : nav_speed_limit;
  bool is_active = show_slc ? (slc_state != static_cast<int>(cereal::LongitudinalPlanSP::SpeedLimitControlState::INACTIVE)) : true;

  bool show_us_style = (!is_metric && show_slc && is_map_speed_limit) || has_us_speed_limit;
  bool show_eu_style = (is_metric && show_slc && is_map_speed_limit) || has_eu_speed_limit;

  QString speedLimitStr = QString::number(std::nearbyint(display_speed));

  // Generate sub-text
  QString sub_text = "";
  if (show_slc) {
    if (slc_state == static_cast<int>(cereal::LongitudinalPlanSP::SpeedLimitControlState::TEMP_INACTIVE)) {
      sub_text = "TEMP";
    } else if (slc_distance > 0) {
      sub_text = QString::number(slc_distance) + (is_metric ? "m" : "f");
    } else if (slc_speed_offset != 0) {
      sub_text = (slc_speed_offset > 0 ? "+" : "") + QString::number(std::nearbyint(slc_speed_offset));
    }
  }

  // US/MUTCD style sign
  if (show_us_style) {
    p.setPen(Qt::NoPen);
    p.setBrush(QColor(255, 255, 255, is_active ? 255 : 85));
    p.drawRoundedRect(sign_rect, 24, 24);
    p.setPen(QPen(QColor(0, 0, 0, is_active ? 255 : 85), 6));
    p.drawRoundedRect(sign_rect.adjusted(9, 9, -9, -9), 16, 16);

    p.setFont(InterFont(28, QFont::DemiBold));
    p.setPen(QColor(0, 0, 0, is_active ? 255 : 85));
    p.drawText(sign_rect.adjusted(0, 22, 0, 0), Qt::AlignTop | Qt::AlignHCenter, tr("SPEED"));
    p.drawText(sign_rect.adjusted(0, 51, 0, 0), Qt::AlignTop | Qt::AlignHCenter, tr("LIMIT"));

    p.setFont(InterFont(70, QFont::Bold));
    p.setPen(over_speed_limit ? QColor(255, 0, 0, 255) : QColor(0, 0, 0, is_active ? 255 : 85));
    p.drawText(sign_rect.adjusted(0, 85, 0, 0), Qt::AlignTop | Qt::AlignHCenter, speedLimitStr);

    if (!sub_text.isEmpty()) {
      p.setFont(InterFont(32, QFont::Bold));
      p.setPen(QColor(0, 0, 0, is_active ? 255 : 85));
      p.drawText(sign_rect.adjusted(0, 85 + 77, 0, 0), Qt::AlignTop | Qt::AlignHCenter, sub_text);
    }
  }

  // EU/Vienna style sign
  if (show_eu_style) {
    p.setPen(Qt::NoPen);
    p.setBrush(QColor(255, 255, 255, is_active ? 255 : 85));
    p.drawEllipse(sign_rect);
    p.setPen(QPen(Qt::red, 20));
    p.drawEllipse(sign_rect.adjusted(16, 16, -16, -16));

    p.setFont(InterFont((speedLimitStr.size() >= 3) ? 60 : 70, QFont::Bold));
    p.setPen(over_speed_limit ? QColor(255, 0, 0, 255) : QColor(0, 0, 0, is_active ? 255 : 85));
    p.drawText(sign_rect, Qt::AlignCenter, speedLimitStr);

    if (!sub_text.isEmpty()) {
      p.setFont(InterFont(25, QFont::Bold));
      p.setPen(QColor(0, 0, 0, is_active ? 255 : 85));
      p.drawText(sign_rect.adjusted(0, 27, 0, 0), Qt::AlignTop | Qt::AlignHCenter, sub_text);
    }
  }

  // Draw map source indicator
  if (show_slc && is_map_speed_limit && (show_us_style || show_eu_style)) {
    p.setOpacity(is_active ? 1.0 : 0.3);
    p.drawPixmap(sign_rect.center().x() - 16, sign_rect.center().y() - 55 - 16, map_img);
    p.setOpacity(1.0);
  }
}
/*
void HudRenderer::drawVisionTurnController(QPainter &p, const QRect &surface_rect) {
  int x = surface_rect.right() - 184 - 24;
  int y = 24;
  int size = 184;

  QColor vtc_color = tcs_colors[static_cast<int>(vtc_state)];
  QString vtc_speed_str = QString::number(std::nearbyint(vtc_speed));

  QRect vtc_rect(x, y, size, size);
  p.setPen(QPen(vtc_color, 10));
  p.setBrush(QColor(0, 0, 0, 100));
  p.drawRoundedRect(vtc_rect, 20, 20);

  p.setFont(InterFont(56, QFont::DemiBold));
  drawCenteredText(p, vtc_rect.center().x(), vtc_rect.center().y(), vtc_speed_str, vtc_color);
}

void HudRenderer::drawTurnSpeedController(QPainter &p, const QRect &surface_rect) {
  // Position below the SLC sign if present, or in default location
  int base_y = 45 + 204; // Base set speed location
  if (show_slc || nav_speed_limit > 0) {
    base_y += 186 + 12; // Add sign height and margin
  }

  int x = 60 + 86; // Center of set speed area
  int y = base_y + 24;
  int width = 184;

  bool is_active = turn_state > cereal::LongitudinalPlanSP::SpeedLimitControlState::TEMP_INACTIVE;

  const QColor border_color = is_active ? QColor(255, 0, 0, 255) : QColor(0, 0, 0, 50);
  const QColor inner_color = QColor(255, 255, 255, is_active ? 255 : 85);
  const QColor text_color = QColor(0, 0, 0, is_active ? 255 : 85);

  // Draw triangular turn speed sign
  const float stroke_w = 15.0;
  const float cS = stroke_w / 2.0 + 4.5;
  const float R = width / 2.0 - stroke_w / 2.0;
  const float A = 0.73205;
  const float h2 = 2.0 * R / (1.0 + A);
  const float h1 = A * h2;
  const float L = 4.0 * R / sqrt(3.0);

  // Draw filled triangle
  QPainterPath path;
  path.moveTo(x, y - R + cS);
  path.lineTo(x - L / 2.0 + cS, y + h1 + h2 - R - stroke_w / 2.0);
  path.lineTo(x + L / 2.0 - cS, y + h1 + h2 - R - stroke_w / 2.0);
  path.closePath();

  p.setPen(Qt::NoPen);
  p.setBrush(inner_color);
  p.drawPath(path);

  // Draw triangle border
  QPainterPath stroke_path;
  stroke_path.moveTo(x, y - R);
  stroke_path.lineTo(x - L / 2.0, y + h1 + h2 - R);
  stroke_path.lineTo(x + L / 2.0, y + h1 + h2 - R);
  stroke_path.closePath();

  p.setPen(QPen(border_color, stroke_w, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
  p.setBrush(Qt::NoBrush);
  p.drawPath(stroke_path);

  // Draw turn direction arrow
  if (turn_sign != 0) {
    p.setOpacity(is_active ? 1.0 : 0.3);
    QPixmap arrow_img = (turn_sign > 0) ? left_img : right_img;
    p.drawPixmap(x - 32, y - R + stroke_w + 30, arrow_img);
    p.setOpacity(1.0);
  }

  // Draw speed text
  QString turn_speed_str = QString::number(std::nearbyint(turn_speed));
  p.setFont(InterFont(67, QFont::Bold));
  drawCenteredText(p, x, y + 25, turn_speed_str, text_color);

  // Draw distance text
  if (turn_distance > 0) {
    QString distance_str = QString::number(turn_distance) + (is_metric ? "m" : "f");
    p.setFont(InterFont(22, QFont::Bold));
    drawCenteredText(p, x, y + 65, distance_str, text_color);
  }
}
*/
void HudRenderer::drawCurrentSpeed(QPainter &p, const QRect &surface_rect) {
  QString speedStr = QString::number(std::nearbyint(speed));

  p.setFont(InterFont(176, QFont::Bold));
  drawText(p, surface_rect.center().x(), 210, speedStr);

  p.setFont(InterFont(66));
  drawText(p, surface_rect.center().x(), 290, is_metric ? tr("km/h") : tr("mph"), 200);
}

void HudRenderer::drawText(QPainter &p, int x, int y, const QString &text, int alpha) {
  QRect real_rect = p.fontMetrics().boundingRect(text);
  real_rect.moveCenter({x, y - real_rect.height() / 2});

  p.setPen(QColor(0xff, 0xff, 0xff, alpha));
  p.drawText(real_rect.x(), real_rect.bottom(), text);
}

void HudRenderer::drawCenteredText(QPainter &p, int x, int y, const QString &text, QColor color) {
  QRect real_rect = p.fontMetrics().boundingRect(text);
  real_rect.moveCenter({x, y});

  p.setPen(color);
  p.drawText(real_rect, Qt::AlignCenter, text);
}