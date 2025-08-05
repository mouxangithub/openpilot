#include "selfdrive/ui/qt/sidebar.h"

#include <QMouseEvent>

#include "selfdrive/ui/qt/util.h"

void Sidebar::drawMetric(QPainter &p, const QPair<QString, QString> &label, QColor c, int y) {
  const QRect rect = {30, y, 240, 126};

  p.setPen(Qt::NoPen);
  p.setBrush(QBrush(c));
  p.setClipRect(rect.x() + 4, rect.y(), 18, rect.height(), Qt::ClipOperation::ReplaceClip);
  p.drawRoundedRect(QRect(rect.x() + 4, rect.y() + 4, 100, 118), 18, 18);
  p.setClipping(false);

  QPen pen = QPen(QColor(0xff, 0xff, 0xff, 0x55));
  pen.setWidth(2);
  p.setPen(pen);
  p.setBrush(Qt::NoBrush);
  p.drawRoundedRect(rect, 20, 20);

  p.setPen(QColor(0xff, 0xff, 0xff));
  p.setFont(InterFont(35, QFont::DemiBold));
  p.drawText(rect.adjusted(22, 0, 0, 0), Qt::AlignCenter, label.first + "\n" + label.second);
}

Sidebar::Sidebar(QWidget *parent) : QFrame(parent), onroad(false), flag_pressed(false), settings_pressed(false) {
  home_img = loadPixmap("../assets/images/button_home.png", home_btn.size());
  flag_img = loadPixmap("../assets/images/button_flag.png", home_btn.size());
  settings_img = loadPixmap("../assets/images/button_settings.png", settings_btn.size(), Qt::IgnoreAspectRatio);
  c3x_img = loadPixmap("../assets/img_c3x.png", home_btn.size());

  connect(this, &Sidebar::valueChanged, [=] { update(); });

  setAttribute(Qt::WA_OpaquePaintEvent);
  setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Expanding);
  setFixedWidth(300);

  QObject::connect(uiState(), &UIState::uiUpdate, this, &Sidebar::updateState);

  pm = std::make_unique<PubMaster>(std::vector<const char*>{"userFlag"});
}

void Sidebar::mousePressEvent(QMouseEvent *event) {
  if (onroad && home_btn.contains(event->pos())) {
    flag_pressed = true;
    update();
  } else if (settings_btn.contains(event->pos())) {
    settings_pressed = true;
    update();
  }
}

void Sidebar::mouseReleaseEvent(QMouseEvent *event) {
  if (flag_pressed || settings_pressed) {
    flag_pressed = settings_pressed = false;
    update();
  }
  if (onroad && home_btn.contains(event->pos())) {
    MessageBuilder msg;
    msg.initEvent().initUserFlag();
    pm->send("userFlag", msg);
  } else if (settings_btn.contains(event->pos())) {
    emit openSettings();
  }
}

void Sidebar::offroadTransition(bool offroad) {
  onroad = !offroad;
  update();
}

void Sidebar::updateState(const UIState &s) {
  if (!isVisible()) return;

  auto &sm = *(s.sm);

  networking = networking ? networking : window()->findChild<Networking *>("");
  bool tethering_on = networking && networking->wifi->tethering_on;
  auto deviceState = sm["deviceState"].getDeviceState();
  setProperty("netType", tethering_on ? "Hotspot": network_type[deviceState.getNetworkType()]);
  int strength = tethering_on ? 4 : (int)deviceState.getNetworkStrength();
  setProperty("netStrength", strength > 0 ? strength + 1 : 0);

  ItemStatus connectStatus;
  auto last_ping = deviceState.getLastAthenaPingTime();
  if (last_ping == 0) {
    connectStatus = ItemStatus{{tr("CONNECT"), tr("OFFLINE")}, warning_color};
  } else {
    connectStatus = nanos_since_boot() - last_ping < 80e9
                        ? ItemStatus{{tr("CONNECT"), tr("ONLINE")}, good_color}
                        : ItemStatus{{tr("CONNECT"), tr("ERROR")}, danger_color};
  }
  setProperty("connectStatus", QVariant::fromValue(connectStatus));

  int maxTempC = deviceState.getMaxTempC();
  QString max_temp = QString::number(maxTempC) + "°C";
  ItemStatus tempStatus = {{tr("TEMP"), max_temp}, danger_color};
  auto ts = deviceState.getThermalStatus();
  if (ts == cereal::DeviceState::ThermalStatus::GREEN) {
    tempStatus = {{tr("TEMP"), max_temp}, good_color};
  } else if (ts == cereal::DeviceState::ThermalStatus::YELLOW) {
    tempStatus = {{tr("TEMP"), max_temp}, warning_color};
  }
  setProperty("tempStatus", QVariant::fromValue(tempStatus));

  ItemStatus pandaStatus = {{tr("VEHICLE"), tr("ONLINE")}, good_color};
  if (s.scene.pandaType == cereal::PandaState::PandaType::UNKNOWN) {
    pandaStatus = {{tr("PANDA"), tr("NO")}, danger_color};
  }
  setProperty("pandaStatus", QVariant::fromValue(pandaStatus));

  capnp::List<int8_t>::Reader cpu_loads = deviceState.getCpuUsagePercent();
  int cpu_usage = cpu_loads.size() != 0 ? std::accumulate(cpu_loads.begin(), cpu_loads.end(), 0) / cpu_loads.size() : 0;
  QString cpu_usages = QString::number(cpu_usage) + "%";
  ItemStatus cputatus = {{tr("CPU"), cpu_usages}, good_color};
  if (cpu_usage >= 85) {
    cputatus = {{tr("CPU"), cpu_usages}, danger_color};
  } else if (cpu_usage >= 70) {
    cputatus = {{tr("CPU"), cpu_usages}, warning_color};
  }
  setProperty("cputatus", QVariant::fromValue(cputatus));

  int gpu_usage = deviceState.getGpuUsagePercent();
  QString gpu_usages = QString::number(gpu_usage) + "%";
  ItemStatus gpuStatus = {{tr("GPU"), gpu_usages}, good_color};
  if (gpu_usage >= 85) {
    gpuStatus = {{tr("GPU"), gpu_usages}, danger_color};
  } else if (gpu_usage >= 70) {
    gpuStatus = {{tr("GPU"), gpu_usages}, warning_color};
  }
  setProperty("gpuStatus", QVariant::fromValue(gpuStatus));

  int memory_usage = deviceState.getMemoryUsagePercent();
  QString memory = QString::number(memory_usage) + "%";
  ItemStatus memoryStatus = {{tr("MEMORY"), memory}, good_color};
  if (memory_usage >= 85) {
    memoryStatus = {{tr("MEMORY"), memory}, danger_color};
  } else if (memory_usage >= 70) {
    memoryStatus = {{tr("MEMORY"), memory}, warning_color};
  }
  setProperty("memoryStatus", QVariant::fromValue(memoryStatus));

  int free_space = deviceState.getFreeSpacePercent();
  QString free_spaces = QString::number(free_space) + "%";
  ItemStatus freeStatus = {{tr("Free Space"), free_spaces}, good_color};
  if (free_space <= 20) {
    freeStatus = {{tr("Free Space"), free_spaces}, danger_color};
  } else if (free_space <= 60) {
    freeStatus = {{tr("Free Space"), free_spaces}, warning_color};
  }
  setProperty("freeStatus", QVariant::fromValue(freeStatus));
}

void Sidebar::paintEvent(QPaintEvent *event) {
  QPainter p(this);
  p.setPen(Qt::NoPen);
  p.setRenderHint(QPainter::Antialiasing);

  p.fillRect(rect(), QColor(57, 57, 57));

  QString c3x_position = QString("%1").arg(QString::fromStdString(params.get("DevicePosition")));

  // buttons
  p.setOpacity(settings_pressed ? 0.65 : 1.0);
  p.drawPixmap(settings_btn.x(), settings_btn.y(), settings_img);
  p.setOpacity(onroad && flag_pressed ? 0.65 : 1.0);
  //p.drawPixmap(home_btn.x(), home_btn.y(), onroad ? flag_img : home_img);
  p.drawPixmap(home_btn.x(), home_btn.y(), c3x_img);

  const QRect r3 = QRect(0, 967, event->rect().width(), 50);
  p.setFont(InterFont(30));
  p.setPen(QColor(0xff, 0xff, 0xff));
  p.drawText(r3, Qt::AlignCenter, c3x_position);

  p.setOpacity(1.0);

  // network
  int x = 58;
  const QColor gray(0x54, 0x54, 0x54);
  for (int i = 0; i < 5; ++i) {
    p.setBrush(i < net_strength ? Qt::white : gray);
    p.drawEllipse(x, 196, 27, 27);
    x += 37;
  }

  p.setFont(InterFont(35));
  p.setPen(QColor(0xff, 0xff, 0xff));
  const QRect r = QRect(58, 247, width() - 100, 50);
  p.drawText(r, Qt::AlignLeft | Qt::AlignVCenter, net_type);

  // metrics
  // drawMetric(p, temp_status.first, temp_status.second, 338);
  // drawMetric(p, panda_status.first, panda_status.second, 496);
  // drawMetric(p, connect_status.first, connect_status.second, 654);

  // drawMetric(p, temp_status.first, temp_status.second, 338);
  drawMetric(p, panda_status.first, panda_status.second, 310);
  drawMetric(p, cpu_status.first, cpu_status.second, 440);
  drawMetric(p, memory_status.first, memory_status.second, 570);
  drawMetric(p, free_status.first, free_status.second, 700);
  // drawMetric(p, gpu_status.first, gpu_status.second, 700);
}
