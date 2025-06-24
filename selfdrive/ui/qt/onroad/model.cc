#include <QPainterPath>
#include "selfdrive/ui/qt/onroad/model.h"

void ModelRenderer::draw(QPainter &painter, const QRect &surface_rect) {
  auto *s = uiState();
  auto &sm = *(s->sm);
  // Check if data is up-to-date
  if (sm.rcv_frame("liveCalibration") < s->scene.started_frame ||
      sm.rcv_frame("modelV2") < s->scene.started_frame) {
    return;
  }

  clip_region = surface_rect.adjusted(-CLIP_MARGIN, -CLIP_MARGIN, CLIP_MARGIN, CLIP_MARGIN);
  experimental_mode = sm["selfdriveState"].getSelfdriveState().getExperimentalMode();
  longitudinal_control = sm["carParams"].getCarParams().getOpenpilotLongitudinalControl();
  path_offset_z = sm["liveCalibration"].getLiveCalibration().getHeight()[0];

  painter.save();

  const auto &model = sm["modelV2"].getModelV2();
  const auto &radar_state = sm["radarState"].getRadarState();
  const auto &lead_one = radar_state.getLeadOne();

  update_model(model, lead_one);
  drawLaneLines(painter);
  drawPath(painter, model, surface_rect);

  if (longitudinal_control && sm.alive("radarState")) {
    update_leads(radar_state, model.getPosition());
    const auto &lead_two = radar_state.getLeadTwo();
    if (lead_one.getStatus()) {
      drawLead(painter, lead_one, lead_vertices[0], surface_rect);
    }
    if (lead_two.getStatus() && (std::abs(lead_one.getDRel() - lead_two.getDRel()) > 3.0)) {
      drawLead(painter, lead_two, lead_vertices[1], surface_rect);
    }
  }

  painter.restore();
}

void ModelRenderer::update_leads(const cereal::RadarState::Reader &radar_state, const cereal::XYZTData::Reader &line) {
  for (int i = 0; i < 2; ++i) {
    const auto &lead_data = (i == 0) ? radar_state.getLeadOne() : radar_state.getLeadTwo();
    if (lead_data.getStatus()) {
      float z = line.getZ()[get_path_length_idx(line, lead_data.getDRel())];
      mapToScreen(lead_data.getDRel(), -lead_data.getYRel(), z + path_offset_z, &lead_vertices[i]);
    }
  }
}

void ModelRenderer::update_model(const cereal::ModelDataV2::Reader &model, const cereal::RadarState::LeadData::Reader &lead) {
  const auto &model_position = model.getPosition();
  float max_distance = std::clamp(*(model_position.getX().end() - 1), MIN_DRAW_DISTANCE, MAX_DRAW_DISTANCE);

  // update lane lines
  const auto &lane_lines = model.getLaneLines();
  const auto &line_probs = model.getLaneLineProbs();
  int max_idx = get_path_length_idx(lane_lines[0], max_distance);
  for (int i = 0; i < std::size(lane_line_vertices); i++) {
    lane_line_probs[i] = line_probs[i];
    mapLineToPolygon(lane_lines[i], 0.025 * lane_line_probs[i], 0, &lane_line_vertices[i], max_idx);
  }

  // update road edges
  const auto &road_edges = model.getRoadEdges();
  const auto &edge_stds = model.getRoadEdgeStds();
  for (int i = 0; i < std::size(road_edge_vertices); i++) {
    road_edge_stds[i] = edge_stds[i];
    mapLineToPolygon(road_edges[i], 0.025, 0, &road_edge_vertices[i], max_idx);
  }

  // update path
  if (lead.getStatus()) {
    const float lead_d = lead.getDRel() * 2.;
    max_distance = std::clamp((float)(lead_d - fmin(lead_d * 0.35, 10.)), 0.0f, max_distance);
  }
  max_idx = get_path_length_idx(model_position, max_distance);
  mapLineToPolygon(model_position, 0.9, path_offset_z, &track_vertices, max_idx, false);
}

void ModelRenderer::drawLaneLines(QPainter &painter) {
  // lanelines
  for (int i = 0; i < std::size(lane_line_vertices); ++i) {
    painter.setBrush(QColor::fromRgbF(1.0, 1.0, 1.0, std::clamp<float>(lane_line_probs[i], 0.0, 0.7)));
    painter.drawPolygon(lane_line_vertices[i]);
  }

  // road edges
  for (int i = 0; i < std::size(road_edge_vertices); ++i) {
    painter.setBrush(QColor::fromRgbF(1.0, 0, 0, std::clamp<float>(1.0 - road_edge_stds[i], 0.0, 1.0)));
    painter.drawPolygon(road_edge_vertices[i]);
  }
}

void ModelRenderer::drawPath(QPainter &painter, const cereal::ModelDataV2::Reader &model, int height, int width) {
  QLinearGradient bg(0, height, 0, 0);
  auto *s = uiState();
  auto &sm = *(s->sm);

  float v_ego = sm["carState"].getCarState().getVEgo();
  bool rainbow = Params().getBool("RainbowMode");

  // Get the current time in seconds for dynamic effect (speed of rainbow movement)
  float time_offset = std::chrono::duration_cast<std::chrono::milliseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count() / 1000.0f;

  if (rainbow) {  // Rainbow Mode
      const int max_len = track_vertices.length();
      bg.setSpread(QGradient::PadSpread);  // Pad for a smooth gradient fade

      for (int i = 0; i < max_len; i += 2) {  // Skip every other point for performance
          if (track_vertices[i].y() < 0 || track_vertices[i].y() > height) continue;

          float lin_grad_point = (height - track_vertices[i].y()) / height;

          // Use easing for smoother color transitions
          float eased_point = pow(lin_grad_point, 1.5f);  // Ease-in effect

          // Dynamic hue with subtle, smooth animation
          float path_hue = fmod(eased_point * 360.0 + (v_ego * 20.0) + (time_offset * 100.0), 360.0);

          // Smooth alpha transition with longer fade
          float alpha = util::map_val(eased_point, 0.2f, 0.75f, 0.8f, 0.0f);

          // Use soft lightness for a premium feel
          bg.setColorAt(eased_point, QColor::fromHslF(path_hue / 360.0, 1.0f, 0.55f, alpha));
      }
  } else if (experimental_mode) {
    // The first half of track_vertices are the points for the right side of the path
    const auto &acceleration = model.getAcceleration().getX();
    const int max_len = std::min<int>(track_vertices.length() / 2, acceleration.size());

    for (int i = 0; i < max_len; ++i) {
      // Some points are out of frame
      int track_idx = max_len - i - 1;  // flip idx to start from bottom right
      if (track_vertices[track_idx].y() < 0 || track_vertices[track_idx].y() > height) continue;

      // Flip so 0 is bottom of frame
      float lin_grad_point = (height - track_vertices[track_idx].y()) / height;

      // speed up: 120, slow down: 0
      float path_hue = fmax(fmin(60 + acceleration[i] * 35, 120), 0);
      // FIXME: painter.drawPolygon can be slow if hue is not rounded
      path_hue = int(path_hue * 100 + 0.5) / 100;

      float saturation = fmin(fabs(acceleration[i] * 1.5), 1);
      float lightness = util::map_val(saturation, 0.0f, 1.0f, 0.95f, 0.62f);        // lighter when grey
      float alpha = util::map_val(lin_grad_point, 0.75f / 2.f, 0.75f, 0.4f, 0.0f);  // matches previous alpha fade
      bg.setColorAt(lin_grad_point, QColor::fromHslF(path_hue / 360., saturation, lightness, alpha));

      // Skip a point, unless next is last
      i += (i + 2) < max_len ? 1 : 0;
    }

  } else {
    updatePathGradient(bg);
  }

  painter.setBrush(bg);
  painter.drawPolygon(track_vertices);
  LongFuel(painter,height, width);
  LateralFuel(painter, height, width);
}


void ModelRenderer::updatePathGradient(QLinearGradient &bg) {
  static const QColor throttle_colors[] = {
      QColor::fromHslF(148. / 360., 0.94, 0.51, 0.4),
      QColor::fromHslF(112. / 360., 1.0, 0.68, 0.35),
      QColor::fromHslF(112. / 360., 1.0, 0.68, 0.0)};

  static const QColor no_throttle_colors[] = {
      QColor::fromHslF(148. / 360., 0.0, 0.95, 0.4),
      QColor::fromHslF(112. / 360., 0.0, 0.95, 0.35),
      QColor::fromHslF(112. / 360., 0.0, 0.95, 0.0),
  };

  // Transition speed; 0.1 corresponds to 0.5 seconds at UI_FREQ
  constexpr float transition_speed = 0.1f;

  // Start transition if throttle state changes
  bool allow_throttle = (*uiState()->sm)["longitudinalPlan"].getLongitudinalPlan().getAllowThrottle() || !longitudinal_control;
  if (allow_throttle != prev_allow_throttle) {
    prev_allow_throttle = allow_throttle;
    // Invert blend factor for a smooth transition when the state changes mid-animation
    blend_factor = std::max(1.0f - blend_factor, 0.0f);
  }

  const QColor *begin_colors = allow_throttle ? no_throttle_colors : throttle_colors;
  const QColor *end_colors = allow_throttle ? throttle_colors : no_throttle_colors;
  if (blend_factor < 1.0f) {
    blend_factor = std::min(blend_factor + transition_speed, 1.0f);
  }

  // Set gradient colors by blending the start and end colors
  bg.setColorAt(0.0f, blendColors(begin_colors[0], end_colors[0], blend_factor));
  bg.setColorAt(0.5f, blendColors(begin_colors[1], end_colors[1], blend_factor));
  bg.setColorAt(1.0f, blendColors(begin_colors[2], end_colors[2], blend_factor));
}

QColor ModelRenderer::blendColors(const QColor &start, const QColor &end, float t) {
  if (t == 1.0f) return end;
  return QColor::fromRgbF(
      (1 - t) * start.redF() + t * end.redF(),
      (1 - t) * start.greenF() + t * end.greenF(),
      (1 - t) * start.blueF() + t * end.blueF(),
      (1 - t) * start.alphaF() + t * end.alphaF());
}

void ModelRenderer::LongFuel(QPainter &painter, int height, int width) {
    qreal rectWidth = static_cast<qreal>(width);
    qreal rectHeight = static_cast<qreal>(height);
    UIState *s = uiState();

    float currentAcceleration = (*s->sm)["carControl"].getCarControl().getActuators().getAccel();
    //float currentAcceleration = (*s->sm)["carState"].getCarState().getAEgo();

    qreal gaugeSize = 140.0;  // Diameter of the semicircle
    qreal backgroundSize = gaugeSize * 1.4;  // Background is 30% larger than the gague
    qreal centerX = rectWidth / 17;  // Center the gague horz
    qreal centerY = rectHeight / 2 + 120;  // Center the gauge vertical offset

    // Draw a dark circular background
    painter.setPen(Qt::NoPen);
    painter.setBrush(QColor(0, 0, 0, 80));  // Semi-transparent black
    painter.drawEllipse(QPointF(centerX, centerY), backgroundSize / 2, backgroundSize / 2);

    // Add a subtle border/glow around the background
    QPen borderPen(QColor(0, 0, 0, 100));
    borderPen.setWidth(2);
    painter.setPen(borderPen);
    painter.drawEllipse(QPointF(centerX, centerY), backgroundSize / 2 + 1, backgroundSize / 2 + 1);

    // Draw the background semicircle
    QPen semicirclePen(QColor(50, 50, 50));  // Dark gray for the semicircle
    semicirclePen.setWidth(30);  // Thicker pen for the semicircle
    semicirclePen.setCapStyle(Qt::RoundCap);
    painter.setPen(semicirclePen);
    painter.drawArc(QRectF(centerX - gaugeSize / 2, centerY - gaugeSize / 2, gaugeSize, gaugeSize), 0, 180 * 16);

    // Determine the color based on the magnitude of acceleration
    QColor indicatorColor;
    float absoluteAcceleration = std::abs(currentAcceleration);
    if (absoluteAcceleration < 0.3) {
        indicatorColor = QColor(23, 241, 66, 200);  // Green for low acceleration
    } else if (absoluteAcceleration < 0.6) {
        indicatorColor = QColor(255, 166, 0, 200);  // Yellow for moderate acceleration
    } else {
        indicatorColor = QColor(245, 0, 0, 200);    // Red for high acceleration
    }

    // Calculate the span of the arc based on acceleration
    int spanAngle = static_cast<int>(90 * absoluteAcceleration * 16);  // Scale for better visibility
    spanAngle = std::clamp(spanAngle, 0, 90 * 16);  // Ensure the arc does not exceed 90 degrees

    // Starting angle is at the middle of the semicircle (90 degrees)
    int startAngle = 90 * 16;

    // Draw the acceleration arc if there's significant acceleration
    if (absoluteAcceleration > 0.01) {
        semicirclePen.setColor(indicatorColor);
        painter.setPen(semicirclePen);

        QRectF arcRect(centerX - gaugeSize / 2, centerY - gaugeSize / 2, gaugeSize, gaugeSize);

        // For positive acceleration, draw the arc to the left
        if (currentAcceleration > 0) {
            painter.drawArc(arcRect, startAngle, -spanAngle);  // Negative span for left side
        } else {
            // For negative acceleration (deceleration), draw the arc to the right
            painter.drawArc(arcRect, startAngle, spanAngle);  // Positive span for right side
        }
    }

    // Draw the text center
    painter.setPen(Qt::white);
    QFont font = painter.font();
    font.setPixelSize(20);
    font.setBold(true);
    painter.setFont(font);
    painter.drawText(QRectF(centerX - 50, centerY + 10, 100, 20), Qt::AlignCenter, "LONG");
}


void ModelRenderer::LateralFuel(QPainter &painter, int height, int width) {
    qreal rectWidth = static_cast<qreal>(width);
    qreal rectHeight = static_cast<qreal>(height);
    UIState *s = uiState();

    float currentLateral = (*s->sm)["carState"].getCarState().getSteeringAngleDeg();

    qreal gaugeSize = 140.0;  // Diameter of the semicircle
    qreal backgroundSize = gaugeSize * 1.4;  // Background is 30% larger than the gague
    qreal centerX = rectWidth / 17;  // Center the gague horz
    qreal centerY = rectHeight / 2 - 120;  // Center the gague vertical offset

    // Draw a dark circular background
    painter.setPen(Qt::NoPen);
    painter.setBrush(QColor(0, 0, 0, 80));  // Semi-transparent black
    painter.drawEllipse(QPointF(centerX, centerY), backgroundSize / 2, backgroundSize / 2);

    // Add a subtle border/glow around the background
    QPen borderPen(QColor(0, 0, 0, 100));
    borderPen.setWidth(2);
    painter.setPen(borderPen);
    painter.drawEllipse(QPointF(centerX, centerY), backgroundSize / 2 + 1, backgroundSize / 2 + 1);

    // Draw the background semicircle
    QPen semicirclePen(QColor(50, 50, 50));  // Dark gray for the semicircle
    semicirclePen.setWidth(30);  // Thicker pen for the semicircle
    semicirclePen.setCapStyle(Qt::RoundCap);
    painter.setPen(semicirclePen);
    painter.drawArc(QRectF(centerX - gaugeSize / 2, centerY - gaugeSize / 2, gaugeSize, gaugeSize), 0, 180 * 16);

    // Determine the color based on the magnitude of lateral force
    QColor indicatorColor;
    float absoluteLateral = std::abs(currentLateral); // TODO: its too choppy, something is wrong here
    if (absoluteLateral < 5.0) {  // Low lateral force
        indicatorColor = QColor(23, 241, 66, 200);  // Green
    } else if (absoluteLateral < 15.0) {  // Moderate lateral force
        indicatorColor = QColor(255, 166, 0, 200);  // Yellow
    } else {  // High lateral force
        indicatorColor = QColor(245, 0, 0, 200);    // Red
    }

    // Calculate the span of the arc based on lateral force
    int spanAngle = static_cast<int>(90 * (absoluteLateral / 15.0) * 16);  // Scale for better visibility
    spanAngle = std::clamp(spanAngle, 0, 90 * 16);  // Ensure the arc does not exceed 90 degrees

    // Starting angle is at the middle of the semicircle (90 degrees)
    int startAngle = 90 * 16;

    // Draw the lateral arc if there's significant lateral force
    if (absoluteLateral > 0.1) {
        semicirclePen.setColor(indicatorColor);
        painter.setPen(semicirclePen);

        QRectF arcRect(centerX - gaugeSize / 2, centerY - gaugeSize / 2, gaugeSize, gaugeSize);

        // For left turn (negative lateral), draw the arc on the left side
        if (currentLateral < 0) {
            painter.drawArc(arcRect, startAngle, -spanAngle);  // Negative span for left side
        }
        // For right turn (positive lateral), draw the arc on the right side
        else {
            painter.drawArc(arcRect, startAngle, spanAngle);  // Positive span for right side
        }
    }

    // Draw the text in the center
    painter.setPen(Qt::white);
    QFont font = painter.font();
    font.setPixelSize(20);
    font.setBold(true);
    painter.setFont(font);
    painter.drawText(QRectF(centerX - 50, centerY + 10, 100, 20), Qt::AlignCenter, "LAT");
}

void ModelRenderer::drawLead(QPainter &painter, const cereal::RadarState::LeadData::Reader &lead_data,
                             const QPointF &vd, const QRect &surface_rect) {
  const float speedBuff = 10.;
  const float leadBuff = 40.;
  const float d_rel = lead_data.getDRel();
  const float v_rel = lead_data.getVRel();

  float fillAlpha = 0;
  if (d_rel < leadBuff) {
    fillAlpha = 255 * (1.0 - (d_rel / leadBuff));
    if (v_rel < 0) {
      fillAlpha += 255 * (-1 * (v_rel / speedBuff));
    }
    fillAlpha = (int)(fmin(fillAlpha, 255));
  }

  float sz = std::clamp((25 * 30) / (d_rel / 3 + 30), 15.0f, 30.0f) * 2.35;
  float raw_x = std::clamp<float>(vd.x(), 0.f, surface_rect.width() - sz / 2);
  float y = std::min<float>(vd.y(), surface_rect.height() - sz * 0.6);

// Check if the change in position is large
  float position_delta = std::abs(raw_x - hysteretic_x);
  float threshold = 100.0f;  // Adjust this value to tune when smoothing kicks in

  if (position_delta > threshold) {
    // For large changes, immediately update position
    hysteretic_x = raw_x;
  } else {
    // For small changes, apply smoothing
    hysteretic_x = (hysteresis_factor * raw_x) + ((1.0f - hysteresis_factor) * hysteretic_x);
  }

  float x = hysteretic_x;  // Use smoothed x value instead of raw_x



  // Set up the pen for drawing
  QPen pen;
  pen.setCapStyle(Qt::RoundCap);  // Round ends of the line
  pen.setJoinStyle(Qt::RoundJoin);  // Round corners

  // Disable fill
  painter.setBrush(Qt::NoBrush);


  // Draw the outer glow effect
  pen.setColor(QColor(218, 202, 37, 255));  // Yellow glow color
  pen.setWidth(10);  // Thicker width for glow
  painter.setPen(pen);

  // Create path for the line
  QPainterPath path;
  path.moveTo(x + (sz * 1.35), y + sz);   // right point
  path.lineTo(x, y); // top point
  path.lineTo(x - (sz * 1.35), y + sz);  // left point

  painter.drawPath(path);  // Draw the glow

  // Draw the main line
  pen.setColor(QColor(201, 34, 49, fillAlpha));  // Red color with calculated opacity
  pen.setWidth(7);  // Slightly thinner than the glow
  painter.setPen(pen);
  painter.drawPath(path);  // Draw the main line

}

// Projects a point in car to space to the corresponding point in full frame image space.
bool ModelRenderer::mapToScreen(float in_x, float in_y, float in_z, QPointF *out) {
  Eigen::Vector3f input(in_x, in_y, in_z);
  auto pt = car_space_transform * input;
  *out = QPointF(pt.x() / pt.z(), pt.y() / pt.z());
  return clip_region.contains(*out);
}

void ModelRenderer::mapLineToPolygon(const cereal::XYZTData::Reader &line, float y_off, float z_off,
                                     QPolygonF *pvd, int max_idx, bool allow_invert) {
  const auto line_x = line.getX(), line_y = line.getY(), line_z = line.getZ();
  QPointF left, right;
  pvd->clear();
  for (int i = 0; i <= max_idx; i++) {
    // highly negative x positions  are drawn above the frame and cause flickering, clip to zy plane of camera
    if (line_x[i] < 0) continue;

    bool l = mapToScreen(line_x[i], line_y[i] - y_off, line_z[i] + z_off, &left);
    bool r = mapToScreen(line_x[i], line_y[i] + y_off, line_z[i] + z_off, &right);
    if (l && r) {
      // For wider lines the drawn polygon will "invert" when going over a hill and cause artifacts
      if (!allow_invert && pvd->size() && left.y() > pvd->back().y()) {
        continue;
      }
      pvd->push_back(left);
      pvd->push_front(right);
    }
  }
}
