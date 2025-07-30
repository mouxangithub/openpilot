#include <cassert>
#include <cmath>
#include <string>
#include <tuple>
#include <vector>
#include <thread> //차선캘리

#include <QDebug>
#include <QProcess>

#include "common/watchdog.h"
#include "common/util.h"
#include "selfdrive/ui/qt/network/networking.h"
#include "selfdrive/ui/qt/offroad/settings.h"
#include "selfdrive/ui/qt/qt_window.h"
#include "selfdrive/ui/qt/widgets/prime.h"
#include "selfdrive/ui/qt/widgets/scrollview.h"
#include "selfdrive/ui/qt/offroad/developer_panel.h"
#include "selfdrive/ui/qt/offroad/firehose.h"

TogglesPanel::TogglesPanel(SettingsWindow *parent) : ListWidget(parent) {
  // param, title, desc, icon
  std::vector<std::tuple<QString, QString, QString, QString>> toggle_defs{
    {
      "OpenpilotEnabledToggle",
      tr("Enable openpilot"),
      tr("Use the openpilot system for adaptive cruise control and lane keep driver assistance. Your attention is required at all times to use this feature. Changing this setting takes effect when the car is powered off."),
      "../assets/img_chffr_wheel.png",
    },
    {
      "ExperimentalMode",
      tr("Experimental Mode"),
      "",
      "../assets/img_experimental_white.svg",
    },
    {
      "DisengageOnAccelerator",
      tr("Disengage on Accelerator Pedal"),
      tr("When enabled, pressing the accelerator pedal will disengage openpilot."),
      "../assets/offroad/icon_disengage_on_accelerator.svg",
    },
    {
      "IsLdwEnabled",
      tr("Enable Lane Departure Warnings"),
      tr("Receive alerts to steer back into the lane when your vehicle drifts over a detected lane line without a turn signal activated while driving over 31 mph (50 km/h)."),
      "../assets/offroad/icon_warning.png",
    },
    {
      "AlwaysOnDM",
      tr("Always-On Driver Monitoring"),
      tr("Enable driver monitoring even when openpilot is not engaged."),
      "../assets/offroad/icon_monitoring.png",
    },
    {
      "RecordFront",
      tr("Record and Upload Driver Camera"),
      tr("Upload data from the driver facing camera and help improve the driver monitoring algorithm."),
      "../assets/offroad/icon_monitoring.png",
    },
    {
      "RecordAudio",
      tr("Record and Upload Microphone Audio"),
      tr("Record and store microphone audio while driving. The audio will be included in the dashcam video in comma connect."),
      "../assets/offroad/microphone.png",
    },
    {
      "IsMetric",
      tr("Use Metric System"),
      tr("Display speed in km/h instead of mph."),
      "../assets/offroad/icon_metric.png",
    },
  };


  std::vector<QString> longi_button_texts{tr("Aggressive"), tr("Standard"), tr("Relaxed") , tr("MoreRelaxed") };
  long_personality_setting = new ButtonParamControl("LongitudinalPersonality", tr("Driving Personality"),
                                          tr("Standard is recommended. In aggressive mode, openpilot will follow lead cars closer and be more aggressive with the gas and brake. "
                                             "In relaxed mode openpilot will stay further away from lead cars. On supported cars, you can cycle through these personalities with "
                                             "your steering wheel distance button."),
                                          "../assets/offroad/icon_speed_limit.png",
                                          longi_button_texts);

  // set up uiState update for personality setting
  QObject::connect(uiState(), &UIState::uiUpdate, this, &TogglesPanel::updateState);

  for (auto &[param, title, desc, icon] : toggle_defs) {
    auto toggle = new ParamControl(param, title, desc, icon, this);

    bool locked = params.getBool((param + "Lock").toStdString());
    toggle->setEnabled(!locked);

    addItem(toggle);
    toggles[param.toStdString()] = toggle;

    // insert longitudinal personality after NDOG toggle
    if (param == "DisengageOnAccelerator") {
      addItem(long_personality_setting);
    }
  }

  // Toggles with confirmation dialogs
  toggles["ExperimentalMode"]->setActiveIcon("../assets/img_experimental.svg");
  toggles["ExperimentalMode"]->setConfirmation(true, true);
}

void TogglesPanel::updateState(const UIState &s) {
  const SubMaster &sm = *(s.sm);

  if (sm.updated("selfdriveState")) {
    auto personality = sm["selfdriveState"].getSelfdriveState().getPersonality();
    if (personality != s.scene.personality && s.scene.started && isVisible()) {
      long_personality_setting->setCheckedButton(static_cast<int>(personality));
    }
    uiState()->scene.personality = personality;
  }
}

void TogglesPanel::expandToggleDescription(const QString &param) {
  toggles[param.toStdString()]->showDescription();
}

void TogglesPanel::showEvent(QShowEvent *event) {
  updateToggles();
}

void TogglesPanel::updateToggles() {
  auto experimental_mode_toggle = toggles["ExperimentalMode"];
  const QString e2e_description = QString("%1<br>"
                                          "<h4>%2</h4><br>"
                                          "%3<br>"
                                          "<h4>%4</h4><br>"
                                          "%5<br>")
                                  .arg(tr("openpilot defaults to driving in <b>chill mode</b>. Experimental mode enables <b>alpha-level features</b> that aren't ready for chill mode. Experimental features are listed below:"))
                                  .arg(tr("End-to-End Longitudinal Control"))
                                  .arg(tr("Let the driving model control the gas and brakes. openpilot will drive as it thinks a human would, including stopping for red lights and stop signs. "
                                          "Since the driving model decides the speed to drive, the set speed will only act as an upper bound. This is an alpha quality feature; "
                                          "mistakes should be expected."))
                                  .arg(tr("New Driving Visualization"))
                                  .arg(tr("The driving visualization will transition to the road-facing wide-angle camera at low speeds to better show some turns. The Experimental mode logo will also be shown in the top right corner."));

  const bool is_release = params.getBool("IsReleaseBranch");
  auto cp_bytes = params.get("CarParamsPersistent");
  if (!cp_bytes.empty()) {
    AlignedBuffer aligned_buf;
    capnp::FlatArrayMessageReader cmsg(aligned_buf.align(cp_bytes.data(), cp_bytes.size()));
    cereal::CarParams::Reader CP = cmsg.getRoot<cereal::CarParams>();

    if (hasLongitudinalControl(CP)) {
      // normal description and toggle
      experimental_mode_toggle->setEnabled(true);
      experimental_mode_toggle->setDescription(e2e_description);
      long_personality_setting->setEnabled(true);
    } else {
      // no long for now
      experimental_mode_toggle->setEnabled(false);
      long_personality_setting->setEnabled(false);
      params.remove("ExperimentalMode");

      const QString unavailable = tr("Experimental mode is currently unavailable on this car since the car's stock ACC is used for longitudinal control.");

      QString long_desc = unavailable + " " + \
                          tr("openpilot longitudinal control may come in a future update.");
      if (CP.getAlphaLongitudinalAvailable()) {
        if (is_release) {
          long_desc = unavailable + " " + tr("An alpha version of openpilot longitudinal control can be tested, along with Experimental mode, on non-release branches.");
        } else {
          long_desc = tr("Enable the openpilot longitudinal control (alpha) toggle to allow Experimental mode.");
        }
      }
      experimental_mode_toggle->setDescription("<b>" + long_desc + "</b><br><br>" + e2e_description);
    }

    experimental_mode_toggle->refresh();
  } else {
    experimental_mode_toggle->setDescription(e2e_description);
  }
}

DevicePanel::DevicePanel(SettingsWindow *parent) : ListWidget(parent) {
  setSpacing(50);
  addItem(new LabelControl(tr("Dongle ID"), getDongleId().value_or(tr("N/A"))));
  addItem(new LabelControl(tr("Serial"), params.get("HardwareSerial").c_str()));

  // power buttons
  QHBoxLayout* power_layout = new QHBoxLayout();
  power_layout->setSpacing(30);

  QPushButton* reboot_btn = new QPushButton(tr("Reboot"));
  reboot_btn->setObjectName("reboot_btn");
  power_layout->addWidget(reboot_btn);
  QObject::connect(reboot_btn, &QPushButton::clicked, this, &DevicePanel::reboot);
  //차선캘리
  QPushButton *reset_CalibBtn = new QPushButton(tr("ReCalibration"));
  reset_CalibBtn->setObjectName("reset_CalibBtn");
  power_layout->addWidget(reset_CalibBtn);
  QObject::connect(reset_CalibBtn, &QPushButton::clicked, this, &DevicePanel::calibration);

  QPushButton* poweroff_btn = new QPushButton(tr("Power Off"));
  poweroff_btn->setObjectName("poweroff_btn");
  power_layout->addWidget(poweroff_btn);
  QObject::connect(poweroff_btn, &QPushButton::clicked, this, &DevicePanel::poweroff);

  if (false && !Hardware::PC()) {
      connect(uiState(), &UIState::offroadTransition, poweroff_btn, &QPushButton::setVisible);
  }

  addItem(power_layout);

  QHBoxLayout* init_layout = new QHBoxLayout();
  init_layout->setSpacing(30);

  QPushButton* init_btn = new QPushButton(tr("Git Pull & Reboot"));
  init_btn->setObjectName("init_btn");
  init_layout->addWidget(init_btn);
  //QObject::connect(init_btn, &QPushButton::clicked, this, &DevicePanel::reboot);
  QObject::connect(init_btn, &QPushButton::clicked, [&]() {
    if (ConfirmationDialog::confirm(tr("Git pull & Reboot?"), tr("Yes"), this)) {
      QString cmd =
        "bash -c 'cd /data/openpilot && "
        "git fetch && "
        "if git status -uno | grep -q \"Your branch is behind\"; then "
        "git pull && reboot; "
        "else "
        "echo \"Already up to date.\"; "
        "fi'";

      if (!QProcess::startDetached(cmd)) {
        ConfirmationDialog::alert(tr("Failed to start update process."), this);
      }
      else {
        ConfirmationDialog::alert(tr("Update process started. Device will reboot if updates are applied."), this);
      }
    }
    });

  QPushButton* default_btn = new QPushButton(tr("Set default"));
  default_btn->setObjectName("default_btn");
  init_layout->addWidget(default_btn);
  //QObject::connect(default_btn, &QPushButton::clicked, this, &DevicePanel::poweroff);
  QObject::connect(default_btn, &QPushButton::clicked, [&]() {
    if (ConfirmationDialog::confirm(tr("Set to default?"), tr("Yes"), this)) {
      //emit parent->closeSettings();
      QTimer::singleShot(1000, []() {
        printf("Set to default\n");
        Params().putInt("SoftRestartTriggered", 2);
        printf("Set to default2\n");
        });
    }
    });

  QPushButton* remove_mapbox_key_btn = new QPushButton(tr("Remove MapboxKey"));
  remove_mapbox_key_btn->setObjectName("remove_mapbox_key_btn");
  init_layout->addWidget(remove_mapbox_key_btn);
  QObject::connect(remove_mapbox_key_btn, &QPushButton::clicked, [&]() {
    if (ConfirmationDialog::confirm(tr("Remove Mapbox key?"), tr("Yes"), this)) {
      QTimer::singleShot(1000, []() {
        Params().put("MapboxPublicKey", "");
        Params().put("MapboxSecretKey", "");
        });
    }
    });

  setStyleSheet(R"(
    #reboot_btn { height: 120px; border-radius: 15px; background-color: #2CE22C; }
    #reboot_btn:pressed { background-color: #24FF24; }
    #reset_CalibBtn { height: 120px; border-radius: 15px; background-color: #FFBB00; }
    #reset_CalibBtn:pressed { background-color: #FF2424; }
    #poweroff_btn { height: 120px; border-radius: 15px; background-color: #E22C2C; }
    #poweroff_btn:pressed { background-color: #FF2424; }
    #init_btn { height: 120px; border-radius: 15px; background-color: #2C2CE2; }
    #init_btn:pressed { background-color: #2424FF; }
    #default_btn { height: 120px; border-radius: 15px; background-color: #BDBDBD; }
    #default_btn:pressed { background-color: #A9A9A9; }
    #remove_mapbox_key_btn { height: 120px; border-radius: 15px; background-color: #BDBDBD; }
    #remove_mapbox_key_btn:pressed { background-color: #A9A9A9; }
  )");
  addItem(init_layout);

  pair_device = new ButtonControl(tr("Pair Device"), tr("PAIR"),
                                  tr("Pair your device with comma connect (connect.comma.ai) and claim your comma prime offer."));
  connect(pair_device, &ButtonControl::clicked, [=]() {
    PairingPopup popup(this);
    popup.exec();
  });
  addItem(pair_device);

  // offroad-only buttons

  auto dcamBtn = new ButtonControl(tr("Driver Camera"), tr("PREVIEW"),
                                   tr("Preview the driver facing camera to ensure that driver monitoring has good visibility. (vehicle must be off)"));
  connect(dcamBtn, &ButtonControl::clicked, [=]() { emit showDriverView(); });
  addItem(dcamBtn);

  auto retrainingBtn = new ButtonControl(tr("Review Training Guide"), tr("REVIEW"), tr("Review the rules, features, and limitations of openpilot"));
  connect(retrainingBtn, &ButtonControl::clicked, [=]() {
    if (ConfirmationDialog::confirm(tr("Are you sure you want to review the training guide?"), tr("Review"), this)) {
      emit reviewTrainingGuide();
    }
  });
  addItem(retrainingBtn);

  auto statusCalibBtn = new ButtonControl(tr("Calibration Status"), tr("SHOW"), "");
  connect(statusCalibBtn, &ButtonControl::showDescriptionEvent, this, &DevicePanel::updateCalibDescription);
  addItem(statusCalibBtn);

  std::string calib_bytes = params.get("CalibrationParams");
  if (!calib_bytes.empty()) {
    try {
      AlignedBuffer aligned_buf;
      capnp::FlatArrayMessageReader cmsg(aligned_buf.align(calib_bytes.data(), calib_bytes.size()));
      auto calib = cmsg.getRoot<cereal::Event>().getLiveCalibration();
      if (calib.getCalStatus() != cereal::LiveCalibrationData::Status::UNCALIBRATED) {
        double pitch = calib.getRpyCalib()[1] * (180 / M_PI);
        double yaw = calib.getRpyCalib()[2] * (180 / M_PI);
        QString position = QString("%2 %1° %4 %3°")
                           .arg(QString::number(std::abs(pitch), 'g', 1), pitch > 0 ? "↓" : "↑",
                                QString::number(std::abs(yaw), 'g', 1), yaw > 0 ? "←" : "→");
        params.put("DevicePosition", position.toStdString());
      }
    } catch (kj::Exception) {
      qInfo() << "invalid CalibrationParams";
    }
  }

  if (Hardware::TICI()) {
    auto regulatoryBtn = new ButtonControl(tr("Regulatory"), tr("VIEW"), "");
    connect(regulatoryBtn, &ButtonControl::clicked, [=]() {
      const std::string txt = util::read_file("../assets/offroad/fcc.html");
      ConfirmationDialog::rich(QString::fromStdString(txt), this);
    });
    addItem(regulatoryBtn);
  }

  auto translateBtn = new ButtonControl(tr("Change Language"), tr("CHANGE"), "");
  connect(translateBtn, &ButtonControl::clicked, [=]() {
    QMap<QString, QString> langs = getSupportedLanguages();
    QString selection = MultiOptionDialog::getSelection(tr("Select a language"), langs.keys(), langs.key(uiState()->language), this);
    if (!selection.isEmpty()) {
      // put language setting, exit Qt UI, and trigger fast restart
      params.put("LanguageSetting", langs[selection].toStdString());
      qApp->exit(18);
      watchdog_kick(0);
    }
  });
  addItem(translateBtn);

  QObject::connect(uiState()->prime_state, &PrimeState::changed, [this] (PrimeState::Type type) {
    pair_device->setVisible(type == PrimeState::PRIME_TYPE_UNPAIRED);
  });
  QObject::connect(uiState(), &UIState::offroadTransition, [=](bool offroad) {
    for (auto btn : findChildren<ButtonControl *>()) {
      if (btn != pair_device) {
        btn->setEnabled(offroad);
      }
    }
    translateBtn->setEnabled(true);
    statusCalibBtn->setEnabled(true);
  });

}

void DevicePanel::updateCalibDescription() {
  QString desc =
      tr("openpilot requires the device to be mounted within 4° left or right and "
         "within 5° up or 9° down. openpilot is continuously calibrating, resetting is rarely required.");
  std::string calib_bytes = params.get("CalibrationParams");
  if (!calib_bytes.empty()) {
    try {
      AlignedBuffer aligned_buf;
      capnp::FlatArrayMessageReader cmsg(aligned_buf.align(calib_bytes.data(), calib_bytes.size()));
      auto calib = cmsg.getRoot<cereal::Event>().getLiveCalibration();
      if (calib.getCalStatus() != cereal::LiveCalibrationData::Status::UNCALIBRATED) {
        double pitch = calib.getRpyCalib()[1] * (180 / M_PI);
        double yaw = calib.getRpyCalib()[2] * (180 / M_PI);
        desc += tr(" Your device is pointed %1° %2 and %3° %4.")
                    .arg(QString::number(std::abs(pitch), 'g', 1), pitch > 0 ? tr("down") : tr("up"),
                         QString::number(std::abs(yaw), 'g', 1), yaw > 0 ? tr("left") : tr("right"));
      }
    } catch (kj::Exception) {
      qInfo() << "invalid CalibrationParams";
    }
  }
  qobject_cast<ButtonControl *>(sender())->setDescription(desc);
}

void DevicePanel::reboot() {
  if (!uiState()->engaged()) {
    if (ConfirmationDialog::confirm(tr("Are you sure you want to reboot?"), tr("Reboot"), this)) {
      // Check engaged again in case it changed while the dialog was open
      if (!uiState()->engaged()) {
        params.putBool("DoReboot", true);
      }
    }
  } else {
    ConfirmationDialog::alert(tr("Disengage to Reboot"), this);
  }
}

//차선캘리
void execAndReboot(const std::string& cmd) {
    system(cmd.c_str());
    Params().putBool("DoReboot", true);
}

void DevicePanel::calibration() {
  if (!uiState()->engaged()) {
    if (ConfirmationDialog::confirm(tr("Are you sure you want to reset calibration?"), tr("ReCalibration"), this)) {
      if (!uiState()->engaged()) {
        std::thread worker(execAndReboot, "cd /data/params/d_tmp;  rm -f CalibrationParams");
        worker.detach();
      }
    }
  } else {
    ConfirmationDialog::alert(tr("Reboot & Disengage to Calibration"), this);
  }
}

void DevicePanel::poweroff() {
  if (!uiState()->engaged()) {
    if (ConfirmationDialog::confirm(tr("Are you sure you want to power off?"), tr("Power Off"), this)) {
      // Check engaged again in case it changed while the dialog was open
      if (!uiState()->engaged()) {
        params.putBool("DoShutdown", true);
      }
    }
  } else {
    ConfirmationDialog::alert(tr("Disengage to Power Off"), this);
  }
}

void SettingsWindow::showEvent(QShowEvent *event) {
  setCurrentPanel(0);
}

void SettingsWindow::setCurrentPanel(int index, const QString &param) {
  if (!param.isEmpty()) {
    // Check if param ends with "Panel" to determine if it's a panel name
    if (param.endsWith("Panel")) {
      QString panelName = param;
      panelName.chop(5); // Remove "Panel" suffix

      // Find the panel by name
      for (int i = 0; i < nav_btns->buttons().size(); i++) {
        if (nav_btns->buttons()[i]->text() == tr(panelName.toStdString().c_str())) {
          index = i;
          break;
        }
      }
    } else {
      emit expandToggleDescription(param);
    }
  }

  panel_widget->setCurrentIndex(index);
  nav_btns->buttons()[index]->setChecked(true);
}

SettingsWindow::SettingsWindow(QWidget *parent) : QFrame(parent) {

  // setup two main layouts
  sidebar_widget = new QWidget;
  QVBoxLayout *sidebar_layout = new QVBoxLayout(sidebar_widget);
  panel_widget = new QStackedWidget();

  // close button
  QPushButton *close_btn = new QPushButton(tr("×"));
  close_btn->setStyleSheet(R"(
    QPushButton {
      font-size: 140px;
      padding-bottom: 20px;
      border-radius: 100px;
      background-color: #292929;
      font-weight: 400;
    }
    QPushButton:pressed {
      background-color: #3B3B3B;
    }
  )");
  close_btn->setFixedSize(200, 200);
  sidebar_layout->addSpacing(45);
  sidebar_layout->addWidget(close_btn, 0, Qt::AlignCenter);
  QObject::connect(close_btn, &QPushButton::clicked, this, &SettingsWindow::closeSettings);

  // setup panels
  DevicePanel *device = new DevicePanel(this);
  QObject::connect(device, &DevicePanel::reviewTrainingGuide, this, &SettingsWindow::reviewTrainingGuide);
  QObject::connect(device, &DevicePanel::showDriverView, this, &SettingsWindow::showDriverView);

  TogglesPanel *toggles = new TogglesPanel(this);
  QObject::connect(this, &SettingsWindow::expandToggleDescription, toggles, &TogglesPanel::expandToggleDescription);

  auto networking = new Networking(this);
  QObject::connect(uiState()->prime_state, &PrimeState::changed, networking, &Networking::setPrimeType);

  QList<QPair<QString, QWidget *>> panels = {
    {tr("Device"), device},
    {tr("Network"), networking},
    {tr("Toggles"), toggles},
  };
  if(Params().getBool("SoftwareMenu")) {
    panels.append({tr("Software"), new SoftwarePanel(this)});
  }
  if(false) {
    panels.append({tr("Firehose"), new FirehosePanel(this)});
  }
  panels.append({ tr("Carrot"), new CarrotPanel(this) });
  panels.append({ tr("Developer"), new DeveloperPanel(this) });

  nav_btns = new QButtonGroup(this);
  for (auto &[name, panel] : panels) {
    QPushButton *btn = new QPushButton(name);
    btn->setCheckable(true);
    btn->setChecked(nav_btns->buttons().size() == 0);
    btn->setStyleSheet(R"(
      QPushButton {
        color: grey;
        border: none;
        background: none;
        font-size: 65px;
        font-weight: 500;
      }
      QPushButton:checked {
        color: white;
      }
      QPushButton:pressed {
        color: #ADADAD;
      }
    )");
    btn->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);
    nav_btns->addButton(btn);
    sidebar_layout->addWidget(btn, 0, Qt::AlignRight);

    const int lr_margin = name != tr("Network") ? 50 : 0;  // Network panel handles its own margins
    panel->setContentsMargins(lr_margin, 25, lr_margin, 25);

    ScrollView *panel_frame = new ScrollView(panel, this);
    panel_widget->addWidget(panel_frame);

    QObject::connect(btn, &QPushButton::clicked, [=, w = panel_frame]() {
      btn->setChecked(true);
      panel_widget->setCurrentWidget(w);
    });
  }
  sidebar_layout->setContentsMargins(50, 50, 100, 50);

  // main settings layout, sidebar + main panel
  QHBoxLayout *main_layout = new QHBoxLayout(this);

  sidebar_widget->setFixedWidth(500);
  main_layout->addWidget(sidebar_widget);
  main_layout->addWidget(panel_widget);

  setStyleSheet(R"(
    * {
      color: white;
      font-size: 50px;
    }
    SettingsWindow {
      background-color: black;
    }
    QStackedWidget, ScrollView {
      background-color: #292929;
      border-radius: 30px;
    }
  )");
}


#include <QScroller>
#include <QListWidget>

static QStringList get_list(const char* path) {
  QStringList stringList;
  QFile textFile(path);
  if (textFile.open(QIODevice::ReadOnly)) {
    QTextStream textStream(&textFile);
    while (true) {
      QString line = textStream.readLine();
      if (line.isNull()) {
        break;
      } else {
        stringList.append(line);
      }
    }
  }
  return stringList;
}

CarrotPanel::CarrotPanel(QWidget* parent) : QWidget(parent) {
  main_layout = new QStackedLayout(this);
  homeScreen = new QWidget(this);
  carrotLayout = new QVBoxLayout(homeScreen);
  carrotLayout->setMargin(40);

  QHBoxLayout* select_layout = new QHBoxLayout();
  select_layout->setSpacing(30);


  QPushButton* start_btn = new QPushButton(tr("Start"));
  start_btn->setObjectName("start_btn");
  QObject::connect(start_btn, &QPushButton::clicked, this, [this]() {
    this->currentCarrotIndex = 0;
    this->togglesCarrot(0);
    updateButtonStyles();
  });

  QPushButton* cruise_btn = new QPushButton(tr("Cruise"));
  cruise_btn->setObjectName("cruise_btn");
  QObject::connect(cruise_btn, &QPushButton::clicked, this, [this]() {
    this->currentCarrotIndex = 1;
    this->togglesCarrot(1);
    updateButtonStyles();
  });

  QPushButton* speed_btn = new QPushButton(tr("Speed"));
  speed_btn->setObjectName("speed_btn");
  QObject::connect(speed_btn, &QPushButton::clicked, this, [this]() {
    this->currentCarrotIndex = 2;
    this->togglesCarrot(2);
    updateButtonStyles();
  });

  QPushButton* latLong_btn = new QPushButton(tr("Tuning"));
  latLong_btn->setObjectName("latLong_btn");
  QObject::connect(latLong_btn, &QPushButton::clicked, this, [this]() {
    this->currentCarrotIndex = 3;
    this->togglesCarrot(3);
    updateButtonStyles();
  });

  QPushButton* disp_btn = new QPushButton(tr("Disp"));
  disp_btn->setObjectName("disp_btn");
  QObject::connect(disp_btn, &QPushButton::clicked, this, [this]() {
    this->currentCarrotIndex = 4;
    this->togglesCarrot(4);
    updateButtonStyles();
  });

  QPushButton* path_btn = new QPushButton(tr("Path"));
  path_btn->setObjectName("path_btn");
  QObject::connect(path_btn, &QPushButton::clicked, this, [this]() {
    this->currentCarrotIndex = 5;
    this->togglesCarrot(5);
    updateButtonStyles();
  });


  updateButtonStyles();

  select_layout->addWidget(start_btn);
  select_layout->addWidget(cruise_btn);
  select_layout->addWidget(speed_btn);
  select_layout->addWidget(latLong_btn);
  select_layout->addWidget(disp_btn);
  select_layout->addWidget(path_btn);
  carrotLayout->addLayout(select_layout, 0);

  QWidget* toggles = new QWidget();
  QVBoxLayout* toggles_layout = new QVBoxLayout(toggles);

  cruiseToggles = new ListWidget(this);
  cruiseToggles->addItem(new CValueControl("CruiseButtonMode", tr("Button: Cruise Button Mode"), tr("0:Normal,1:User1,2:User2"), "../assets/offroad/icon_road.png", 0, 2, 1));
  cruiseToggles->addItem(new CValueControl("LfaButtonMode", tr("Button: LFA Button Mode"), tr("0:Normal,1:Decel&Stop&LeadCarReady"), "../assets/offroad/icon_road.png", 0, 1, 1));
  cruiseToggles->addItem(new CValueControl("CruiseSpeedUnit", tr("Button: Cruise Speed Unit"), "", "../assets/offroad/icon_road.png", 1, 20, 1));
  cruiseToggles->addItem(new CValueControl("CruiseEcoControl", tr("CRUISE: Eco control(4km/h)"), tr("Temporarily increasing the set speed to improve fuel efficiency."), "../assets/offroad/icon_road.png", 0, 10, 1));
  //cruiseToggles->addItem(new CValueControl("CruiseSpeedMin", tr("CRUISE: Speed Lower limit(10)"), tr("Cruise control MIN speed"), "../assets/offroad/icon_road.png", 5, 50, 1));
  cruiseToggles->addItem(new CValueControl("AutoSpeedUptoRoadSpeedLimit", tr("CRUISE: Auto speed up (0%)"), tr("Auto speed up based on the lead car up to RoadSpeedLimit."), "../assets/offroad/icon_road.png", 0, 200, 10));
  //cruiseToggles->addItem(new CValueControl("AutoResumeFromGas", tr("GAS CRUISE ON: Use"), tr("Auto Cruise on when GAS pedal released, 60% Gas Cruise On automatically"), "../assets/offroad/icon_road.png", 0, 3, 1));
  //cruiseToggles->addItem(new CValueControl("AutoResumeFromGasSpeed", tr("GAS CRUISE ON: Speed(30)"), tr("Driving speed exceeds the set value, Cruise ON"), "../assets/offroad/icon_road.png", 20, 140, 5));
  //cruiseToggles->addItem(new CValueControl("TFollowSpeedAddM", tr("GAP: Additional TFs 40km/h(0)x0.01s"), tr("Speed-dependent additional max(100km/h) TFs"), "../assets/offroad/icon_road.png", -100, 200, 5));
  //cruiseToggles->addItem(new CValueControl("TFollowSpeedAdd", tr("GAP: Additional TFs 100Km/h(0)x0.01s"), tr("Speed-dependent additional max(100km/h) TFs"), "../assets/offroad/icon_road.png", -100, 200, 5));
  cruiseToggles->addItem(new CValueControl("TFollowGap1", tr("GAP1: Apply TFollow (110)x0.01s"), "", "../assets/offroad/icon_road.png", 70, 300, 5));
  cruiseToggles->addItem(new CValueControl("TFollowGap2", tr("GAP2: Apply TFollow (120)x0.01s"), "", "../assets/offroad/icon_road.png", 70, 300, 5));
  cruiseToggles->addItem(new CValueControl("TFollowGap3", tr("GAP3: Apply TFollow (160)x0.01s"), "", "../assets/offroad/icon_road.png", 70, 300, 5));
  cruiseToggles->addItem(new CValueControl("TFollowGap4", tr("GAP4: Apply TFollow (180)x0.01s"), "", "../assets/offroad/icon_road.png", 70, 300, 5));
  cruiseToggles->addItem(new CValueControl("DynamicTFollow", tr("Dynamic GAP control"), "", "../assets/offroad/icon_road.png", 0, 100, 5));
  cruiseToggles->addItem(new CValueControl("DynamicTFollowLC", tr("Dynamic GAP control (LaneChange)"), "", "../assets/offroad/icon_road.png", 0, 100, 5));
  cruiseToggles->addItem(new CValueControl("MyDrivingMode", tr("DRIVEMODE: Select"), tr("1:ECO,2:SAFE,3:NORMAL,4:HIGH"), "../assets/offroad/icon_road.png", 1, 4, 1));
  cruiseToggles->addItem(new CValueControl("MyDrivingModeAuto", tr("DRIVEMODE: Auto"), tr("NORMAL mode only"), "../assets/offroad/icon_road.png", 0, 1, 1));
  cruiseToggles->addItem(new CValueControl("TrafficLightDetectMode", tr("TrafficLight DetectMode"), tr("0:None, 1:Stopping only, 2: Stop & Go"), "../assets/offroad/icon_road.png", 0, 2, 1));
  //cruiseToggles->addItem(new CValueControl("MyEcoModeFactor", "DRIVEMODE: ECO Accel ratio(80%)", "Acceleration ratio in ECO mode", "../assets/offroad/icon_road.png", 10, 95, 5));
  //cruiseToggles->addItem(new CValueControl("MySafeModeFactor", "DRIVEMODE: SAFE ratio(60%)", "Accel/StopDistance/DecelRatio/Gap control ratio", "../assets/offroad/icon_road.png", 10, 90, 10));
  //cruiseToggles->addItem(new CValueControl("MyHighModeFactor", "DRIVEMODE: HIGH ratio(100%)", "AccelRatio control ratio", "../assets/offroad/icon_road.png", 100, 300, 10));

  latLongToggles = new ListWidget(this);
  //latLongToggles->addItem(new CValueControl("AutoLaneChangeSpeed", tr("LaneChangeSpeed(20)"), "", "../assets/offroad/icon_road.png", 1, 100, 5));
  latLongToggles->addItem(new CValueControl("UseLaneLineSpeed", tr("Laneline mode speed(0)"), tr("Laneline mode, lat_mpc control used"), "../assets/offroad/icon_logic.png", 0, 200, 5));
  latLongToggles->addItem(new CValueControl("UseLaneLineCurveSpeed", tr("Laneline mode curve speed(0)"), tr("Laneline mode, high speed only"), "../assets/offroad/icon_logic.png", 0, 200, 5));
  latLongToggles->addItem(new CValueControl("AdjustLaneOffset", tr("AdjustLaneOffset(0)cm"), "", "../assets/offroad/icon_logic.png", 0, 500, 5));
  latLongToggles->addItem(new CValueControl("CustomSR", tr("LAT: SteerRatiox0.1(0)"), tr("Custom SteerRatio"), "../assets/offroad/icon_logic.png", 0, 300, 1));
  latLongToggles->addItem(new CValueControl("SteerRatioRate", tr("LAT: SteerRatioRatex0.01(100)"), tr("SteerRatio apply rate"), "../assets/offroad/icon_logic.png", 30, 170, 1));
  latLongToggles->addItem(new CValueControl("PathOffset", tr("LAT: PathOffset"), tr("(-)left, (+)right"), "../assets/offroad/icon_logic.png", -150, 150, 1));
  //latLongToggles->addItem(horizontal_line());
  //latLongToggles->addItem(new CValueControl("JerkStartLimit", tr("LONG: JERK START(10)x0.1"), tr("Starting Jerk."), "../assets/offroad/icon_road.png", 1, 50, 1));
  //latLongToggles->addItem(new CValueControl("LongitudinalTuningApi", tr("LONG: ControlType"), tr("0:velocity pid, 1:accel pid, 2:accel pid(comma)"), "../assets/offroad/icon_road.png", 0, 2, 1));
  latLongToggles->addItem(new CValueControl("LongTuningKpV", tr("LONG: P Gain(100)"), "", "../assets/offroad/icon_logic.png", 0, 150, 5));
  latLongToggles->addItem(new CValueControl("LongTuningKiV", tr("LONG: I Gain(0)"), "", "../assets/offroad/icon_logic.png", 0, 2000, 5));
  latLongToggles->addItem(new CValueControl("LongTuningKf", tr("LONG: FF Gain(100)"), "", "../assets/offroad/icon_logic.png", 0, 200, 5));
  latLongToggles->addItem(new CValueControl("LongActuatorDelay", tr("LONG: ActuatorDelay(20)"), "", "../assets/offroad/icon_logic.png", 0, 200, 5));
  latLongToggles->addItem(new CValueControl("VEgoStopping", tr("LONG: VEgoStopping(50)"), tr("Stopping factor"), "../assets/offroad/icon_logic.png", 1, 100, 5));
  latLongToggles->addItem(new CValueControl("RadarReactionFactor", tr("LONG: Radar reaction factor(100)"), "", "../assets/offroad/icon_logic.png", 0, 200, 10));
  //latLongToggles->addItem(new CValueControl("StartAccelApply", tr("LONG: StartingAccel 2.0x(0)%"), tr("정지->출발시 가속도의 가속율을 지정합니다 0: 사용안함."), "../assets/offroad/icon_road.png", 0, 100, 10));
  //latLongToggles->addItem(new CValueControl("StopAccelApply", tr("LONG: StoppingAccel -2.0x(0)%"), tr("정지유지시 브레이크압을 조정합니다. 0: 사용안함. "), "../assets/offroad/icon_road.png", 0, 100, 10));
  latLongToggles->addItem(new CValueControl("LaneChangeNeedTorque", tr("LaneChange need torque"), tr("-1:Disable lanechange, 0: no need torque, 1:need torque"), "../assets/offroad/icon_logic.png", -1, 1, 1));
  latLongToggles->addItem(new CValueControl("LaneChangeDelay", tr("LaneChange delay"), tr("x0.1sec"), "../assets/offroad/icon_logic.png", 0, 100, 5));
  latLongToggles->addItem(new CValueControl("LaneChangeBsd", tr("LaneChange Bsd"), tr("-1:ignore bsd, 0:BSD detect, 1: block steer torque"), "../assets/offroad/icon_logic.png", -1, 1, 1));
  latLongToggles->addItem(new CValueControl("StoppingAccel", tr("LONG: StoppingStartAccelx0.01(-40)"), "", "../assets/offroad/icon_logic.png", -100, 0, 5));
  latLongToggles->addItem(new CValueControl("StopDistanceCarrot", tr("LONG: StopDistance (600)cm"), "", "../assets/offroad/icon_logic.png", 300, 1000, 10));
  //latLongToggles->addItem(new CValueControl("TraffStopDistanceAdjust", tr("LONG: TrafficStopDistance adjust(150)cm"), "", "../assets/offroad/icon_road.png", -1000, 1000, 10));
  latLongToggles->addItem(new CValueControl("JLeadFactor3", tr("LONG: Jerk Lead Factor (0)"), tr("x0.01"), "../assets/offroad/icon_logic.png", 0, 100, 5));
  latLongToggles->addItem(new CValueControl("CruiseMaxVals0", tr("ACCEL:0km/h(160)"), tr("Acceleration needed at specified speed.(x0.01m/s^2)"), "../assets/offroad/icon_logic.png", 1, 250, 5));
  latLongToggles->addItem(new CValueControl("CruiseMaxVals1", tr("ACCEL:10km/h(160)"), tr("Acceleration needed at specified speed.(x0.01m/s^2)"), "../assets/offroad/icon_logic.png", 1, 250, 5));
  latLongToggles->addItem(new CValueControl("CruiseMaxVals2", tr("ACCEL:40km/h(120)"), tr("Acceleration needed at specified speed.(x0.01m/s^2)"), "../assets/offroad/icon_logic.png", 1, 250, 5));
  latLongToggles->addItem(new CValueControl("CruiseMaxVals3", tr("ACCEL:60km/h(100)"), tr("Acceleration needed at specified speed.(x0.01m/s^2)"), "../assets/offroad/icon_logic.png", 1, 250, 5));
  latLongToggles->addItem(new CValueControl("CruiseMaxVals4", tr("ACCEL:80km/h(80)"), tr("Acceleration needed at specified speed.(x0.01m/s^2)"), "../assets/offroad/icon_logic.png", 1, 250, 5));
  latLongToggles->addItem(new CValueControl("CruiseMaxVals5", tr("ACCEL:110km/h(70)"), tr("Acceleration needed at specified speed.(x0.01m/s^2)"), "../assets/offroad/icon_logic.png", 1, 250, 5));
  latLongToggles->addItem(new CValueControl("CruiseMaxVals6", tr("ACCEL:140km/h(60)"), tr("Acceleration needed at specified speed.(x0.01m/s^2)"), "../assets/offroad/icon_logic.png", 1, 250, 5));
  //latLongToggles->addItem(new CValueControl("CruiseMinVals", tr("DECEL:(120)"), tr("Sets the deceleration rate.(x0.01m/s^2)"), "../assets/offroad/icon_road.png", 50, 250, 5));
  latLongToggles->addItem(new CValueControl("MaxAngleFrames", tr("MaxAngleFrames(89)"), tr("89:Basic, steering instrument panel error 85~87"), "../assets/offroad/icon_logic.png", 80, 100, 1));
  latLongToggles->addItem(new CValueControl("SteerActuatorDelay", tr("LAT:SteerActuatorDelay(30)"), tr("x0.01, 0:LiveDelay"), "../assets/offroad/icon_logic.png", 0, 100, 1));
  latLongToggles->addItem(new CValueControl("LateralTorqueCustom", tr("LAT: TorqueCustom(0)"), "", "../assets/offroad/icon_logic.png", 0, 2, 1));
  latLongToggles->addItem(new CValueControl("LateralTorqueAccelFactor", tr("LAT: TorqueAccelFactor(2500)"), "", "../assets/offroad/icon_logic.png", 1000, 6000, 10));
  latLongToggles->addItem(new CValueControl("LateralTorqueFriction", tr("LAT: TorqueFriction(100)"), "", "../assets/offroad/icon_logic.png", 0, 1000, 10));
  latLongToggles->addItem(new CValueControl("CustomSteerMax", tr("LAT: CustomSteerMax(0)"), "", "../assets/offroad/icon_logic.png", 0, 30000, 5));
  latLongToggles->addItem(new CValueControl("CustomSteerDeltaUp", tr("LAT: CustomSteerDeltaUp(0)"), "", "../assets/offroad/icon_logic.png", 0, 50, 1));
  latLongToggles->addItem(new CValueControl("CustomSteerDeltaDown", tr("LAT: CustomSteerDeltaDown(0)"), "", "../assets/offroad/icon_logic.png", 0, 50, 1));

  dispToggles = new ListWidget(this);
  //dispToggles->addItem(new CValueControl("ShowHudMode", tr("DISP:Display Mode"), tr("0:Frog,1:APilot,2:Bottom,3:Top,4:Left,5:Left-Bottom"), "../assets/offroad/icon_shell.png", 0, 5, 1));
  dispToggles->addItem(new CValueControl("ShowDebugUI", tr("DISP:Debug Info"), "", "../assets/offroad/icon_shell.png", 0, 2, 1));
  dispToggles->addItem(new CValueControl("ShowTpms", tr("DISP:Tpms Info"), "", "../assets/offroad/icon_shell.png", 0, 3, 1));
  dispToggles->addItem(new CValueControl("ShowDateTime", tr("DISP:Time Info"), tr("0:None,1:Time/Date,2:Time,3:Date"), "../assets/offroad/icon_calendar.png", 0, 3, 1));
  //dispToggles->addItem(new CValueControl("ShowSteerRotate", tr("DISP:Handle rotate"), tr("0:None,1:Rotate"), "../assets/offroad/icon_shell.png", 0, 1, 1));
  dispToggles->addItem(new CValueControl("ShowPathEnd", tr("DISP:Path End"), tr("0:None,1:Display"), "../assets/offroad/icon_shell.png", 0, 1, 1));
  //dispToggles->addItem(new CValueControl("ShowAccelRpm", tr("DISP:Accel meter"), tr("0:None,1:Display,1:Accel+RPM"), "../assets/offroad/icon_shell.png", 0, 2, 1));
  //dispToggles->addItem(new CValueControl("ShowTpms", tr("DISP:TPMS"), tr("0:None,1:Display"), "../assets/offroad/icon_shell.png", 0, 1, 1));
  //dispToggles->addItem(new CValueControl("ShowSteerMode", tr("DISP:Handle Display Mode"), tr("0:Black,1:Color,2:None"), "../assets/offroad/icon_shell.png", 0, 2, 1));
  dispToggles->addItem(new CValueControl("ShowDeviceState", tr("DISP:Device State"), tr("0:None,1:Display"), "../assets/offroad/icon_shell.png", 0, 1, 1));
  //dispToggles->addItem(new CValueControl("ShowConnInfo", tr("DISP:APM connection"), tr("0:NOne,1:Display"), "../assets/offroad/icon_shell.png", 0, 1, 1));
  dispToggles->addItem(new CValueControl("ShowLaneInfo", tr("DISP:Lane Info"), tr("-1:None, 0:Path, 1:Path+Lane, 2: Path+Lane+RoadEdge"), "../assets/offroad/icon_shell.png", -1, 2, 1));
  //dispToggles->addItem(new CValueControl("ShowBlindSpot", tr("DISP:BSD Info"), tr("0:None,1:Display"), "../assets/offroad/icon_shell.png", 0, 1, 1));
  //dispToggles->addItem(new CValueControl("ShowGapInfo", tr("DISP:GAP Info"), tr("0:None,1:Display"), "../assets/offroad/icon_shell.png", -1, 1, 1));
  //dispToggles->addItem(new CValueControl("ShowDmInfo", tr("DISP:DM Info"), tr("0:None,1:Display,-1:Disable(Reboot)"), "../assets/offroad/icon_shell.png", -1, 1, 1));
  dispToggles->addItem(new CValueControl("ShowRadarInfo", tr("DISP:Radar Info"), tr("0:None,1:Display,2:RelPos,3:Stopped Car"), "../assets/offroad/icon_shell.png", 0, 3, 1));
  dispToggles->addItem(new CValueControl("ShowRouteInfo", tr("DISP:Route Info"), tr("0:None,1:Display"), "../assets/offroad/icon_shell.png", 0, 1, 1));
  dispToggles->addItem(new CValueControl("ShowPlotMode", tr("DISP:Debug plot"), "", "../assets/offroad/icon_shell.png", 0, 10, 1));
  dispToggles->addItem(new CValueControl("ShowCustomBrightness", tr("Brightness ratio"), "", "../assets/offroad/icon_brightness.png", 0, 100, 10));

  pathToggles = new ListWidget(this);
  pathToggles->addItem(new CValueControl("ShowPathModeCruiseOff", tr("DISP: Path Mode: Cruise OFF"), tr("0:Normal,1,2:Rec,3,4:^^,5,6:Rec,7,8:^^,9,10,11,12:Smooth^^"), "../assets/offroad/icon_shell.png", 0, 15, 1));
  pathToggles->addItem(new CValueControl("ShowPathColorCruiseOff", tr("DISP: Path Color: Cruise OFF"), tr("(+10:Stroke)0:Red,1:Orange,2:Yellow,3:Green,4:Blue,5:Indigo,6:Violet,7:Brown,8:White,9:Black"), "../assets/offroad/icon_shell.png", 0, 19, 1));
  pathToggles->addItem(new CValueControl("ShowPathMode", tr("DISP:Path Mode: Laneless"), tr("0:Normal,1,2:Rec,3,4:^^,5,6:Rec,7,8:^^,9,10,11,12:Smooth^^"), "../assets/offroad/icon_shell.png", 0, 15, 1));
  pathToggles->addItem(new CValueControl("ShowPathColor", tr("DISP:Path Color: Laneless"), tr("(+10:Stroke)0:Red,1:Orange,2:Yellow,3:Green,4:Blue,5:Indigo,6:Violet,7:Brown,8:White,9:Black"), "../assets/offroad/icon_shell.png", 0, 19, 1));
  pathToggles->addItem(new CValueControl("ShowPathModeLane", tr("DISP:Path Mode: LaneMode"), tr("0:Normal,1,2:Rec,3,4:^^,5,6:Rec,7,8:^^,9,10,11,12:Smooth^^"), "../assets/offroad/icon_shell.png", 0, 15, 1));
  pathToggles->addItem(new CValueControl("ShowPathColorLane", tr("DISP:Path Color: LaneMode"), tr("(+10:Stroke)0:Red,1:Orange,2:Yellow,3:Green,4:Blue,5:Indigo,6:Violet,7:Brown,8:White,9:Black"), "../assets/offroad/icon_shell.png", 0, 19, 1));
  pathToggles->addItem(new CValueControl("ShowPathWidth", tr("DISP:Path Width ratio(100%)"), "", "../assets/offroad/icon_shell.png", 10, 200, 10));

  startToggles = new ListWidget(this);
  QString selected = QString::fromStdString(Params().get("CarSelected3"));
  QPushButton* selectCarBtn = new QPushButton(selected.length() > 1 ? selected : tr("SELECT YOUR CAR"));
  selectCarBtn->setObjectName("selectCarBtn");
  selectCarBtn->setStyleSheet(R"(
    QPushButton {
      margin-top: 20px; margin-bottom: 20px; padding: 10px; height: 120px; border-radius: 15px;
      color: #FFFFFF; background-color: #2C2CE2;
    }
    QPushButton:pressed {
      background-color: #2424FF;
    }
  )");
  //selectCarBtn->setFixedSize(350, 100);
  connect(selectCarBtn, &QPushButton::clicked, [=]() {
    QString selected = QString::fromStdString(Params().get("CarSelected3"));

    QStringList all_items = get_list((QString::fromStdString(Params().getParamPath()) + "/SupportedCars").toStdString().c_str());
    all_items.append(get_list((QString::fromStdString(Params().getParamPath()) + "/SupportedCars_gm").toStdString().c_str()));
    all_items.append(get_list((QString::fromStdString(Params().getParamPath()) + "/SupportedCars_toyota").toStdString().c_str()));
    all_items.append(get_list((QString::fromStdString(Params().getParamPath()) + "/SupportedCars_mazda").toStdString().c_str()));

    QMap<QString, QStringList> car_groups;
    for (const QString& car : all_items) {
      QStringList parts = car.split(" ", QString::SkipEmptyParts);
      if (!parts.isEmpty()) {
        QString manufacturer = parts.first();
        car_groups[manufacturer].append(car);
      }
    }

    QStringList manufacturers = car_groups.keys();
    QString selectedManufacturer = MultiOptionDialog::getSelection("Select Manufacturer", manufacturers, manufacturers.isEmpty() ? "" : manufacturers.first(), this);

    if (!selectedManufacturer.isEmpty()) {
      QStringList cars = car_groups[selectedManufacturer];
      QString selectedCar = MultiOptionDialog::getSelection("Select your car", cars, selected, this);

      if (!selectedCar.isEmpty()) {
        if (selectedCar == "[ Not Selected ]") {
          Params().remove("CarSelected3");
        } else {
          printf("Selected Car: %s\n", selectedCar.toStdString().c_str());
          Params().put("CarSelected3", selectedCar.toStdString());
          QTimer::singleShot(1000, []() {
            Params().putInt("SoftRestartTriggered", 1);
          });
          ConfirmationDialog::alert(selectedCar, this);
        }
        selected = QString::fromStdString(Params().get("CarSelected3"));
        selectCarBtn->setText((selected.isEmpty() || selected == "[ Not Selected ]") ? tr("SELECT YOUR CAR") : selected);
      }
    }
  });

  startToggles->addItem(selectCarBtn);
  startToggles->addItem(new CValueControl("HyundaiCameraSCC", tr("HYUNDAI: CAMERA SCC"), tr("1:Connect the SCC's CAN line to CAM, 2:Sync Cruise state, 3:StockLong"), "../assets/offroad/icon_shell.png", 0, 3, 1));
  startToggles->addItem(new ParamControl("IsLdwsCar", tr("IsLdwsCar"), "", "../assets/offroad/icon_road.png", this));
  startToggles->addItem(new CValueControl("EnableRadarTracks", tr("Enable Radar Track"), tr("1:Enable RadarTrack, -1,2:Disable use HKG SCC radar at all times"), "../assets/offroad/icon_shell.png", -1, 2, 1));
  startToggles->addItem(new CValueControl("CanfdHDA2", tr("CANFD: HDA2 mode"), tr("1:HDA2,2:HDA2+BSM"), "../assets/offroad/icon_shell.png", 0, 2, 1));
  startToggles->addItem(new CValueControl("AutoCruiseControl", tr("Auto Cruise control"), tr("Softhold, Auto Cruise ON/OFF control"), "../assets/offroad/icon_road.png", 0, 3, 1));
  startToggles->addItem(new CValueControl("CruiseOnDist", tr("CRUISE: Auto ON distance(0cm)"), tr("When GAS/Brake is OFF, Cruise ON when the lead car gets closer."), "../assets/offroad/icon_road.png", 0, 2500, 50));
  startToggles->addItem(new CValueControl("AutoEngage", tr("Auto Engage control on start"), tr("1:SteerEnable, 2:Steer/Cruise Engage"), "../assets/offroad/icon_road.png", 0, 2, 1));
  startToggles->addItem(new ParamControl("DisableMinSteerSpeed", tr("Disable Min.SteerSpeed (Eg. SMDPS"), "", "../assets/offroad/icon_road.png", this));
  startToggles->addItem(new CValueControl("AutoGasTokSpeed", tr("Auto AccelTok speed"), tr("Gas(Accel)Tok enable speed"), "../assets/offroad/icon_road.png", 0, 200, 5));
  startToggles->addItem(new ParamControl("AutoGasSyncSpeed", tr("Auto update Cruise speed"), "", "../assets/offroad/icon_road.png", this));
  startToggles->addItem(new CValueControl("SpeedFromPCM", tr("Read Cruise Speed from PCM"), tr("Toyota must set to 1, Honda 3"), "../assets/offroad/icon_road.png", 0, 3, 1));
  startToggles->addItem(new CValueControl("SoundVolumeAdjust", tr("Sound Volume(100%)"), "", "../assets/offroad/icon_sound.png", 5, 200, 5));
  startToggles->addItem(new CValueControl("SoundVolumeAdjustEngage", tr("Sound Volume, Engage(10%)"), "", "../assets/offroad/icon_sound.png", 5, 200, 5));
  startToggles->addItem(new CValueControl("MaxTimeOffroadMin", tr("Power off time (min)"), "", "../assets/offroad/icon_sandtimer.png", 1, 600, 10));
  startToggles->addItem(new ParamControl("DisableDM", tr("Disable DM"), "", "../assets/img_driver_face_static_x.png", this));
  startToggles->addItem(new CValueControl("EnableConnect", tr("EnableConnect"), tr("Your device may be banned by Comma"), "../assets/offroad/icon_sandtimer.png", 0, 1, 1));
  //startToggles->addItem(new CValueControl("CarrotCountDownSpeed", tr("NaviCountDown Speed(10)"), "", "../assets/offroad/icon_shell.png", 0, 200, 5));
  startToggles->addItem(new CValueControl("MapboxStyle", tr("Mapbox Style(0)"), "", "../assets/offroad/icon_shell.png", 0, 2, 1));
  startToggles->addItem(new CValueControl("RecordRoadCam", tr("Record Road camera(0)"), tr("1:RoadCam, 2:RoadCam+WideRoadCam"), "../assets/offroad/icon_shell.png", 0, 2, 1));
  startToggles->addItem(new CValueControl("HDPuse", tr("Use HDP(CCNC)(0)"), tr("1:While Using APN, 2:Always"), "../assets/offroad/icon_shell.png", 0, 2, 1));
  startToggles->addItem(new ParamControl("HotspotOnBoot", tr("Hotspot enabled on boot"), "", "../assets/offroad/icon_shell.png", this));
  startToggles->addItem(new ParamControl("SoftwareMenu", tr("Enable Software Menu"), "", "../assets/offroad/icon_shell.png", this));
  //startToggles->addItem(new ParamControl("NoLogging", tr("Disable Logger"), "", "../assets/offroad/icon_shell.png", this));
  //startToggles->addItem(new ParamControl("LaneChangeNeedTorque", tr("LaneChange: Need Torque"), "", "../assets/offroad/icon_shell.png", this));
  //startToggles->addItem(new CValueControl("LaneChangeLaneCheck", tr("LaneChange: Check lane exist"), tr("(0:No,1:Lane,2:+Edge)"), "../assets/offroad/icon_shell.png", 0, 2, 1));
  startToggles->addItem(new CValueControl("NNFF", tr("NNFF"), tr("Twilsonco's NNFF(Reboot required)"), "../assets/offroad/icon_road.png", 0, 1, 1));
  startToggles->addItem(new CValueControl("NNFFLite", tr("NNFFLite"), tr("Twilsonco's NNFF-Lite(Reboot required)"), "../assets/offroad/icon_road.png", 0, 1, 1));

  speedToggles = new ListWidget(this);
  speedToggles->addItem(new CValueControl("AutoCurveSpeedLowerLimit", tr("CURVE: Lower limit speed(30)"), tr("When you approach a curve, reduce your speed. Minimum speed"), "../assets/offroad/icon_road.png", 30, 200, 5));
  speedToggles->addItem(new CValueControl("AutoCurveSpeedFactor", tr("CURVE: Auto Control ratio(100%)"), "", "../assets/offroad/icon_road.png", 50, 300, 1));
  speedToggles->addItem(new CValueControl("AutoCurveSpeedAggressiveness", tr("CURVE: Aggressiveness (100%)"), "", "../assets/offroad/icon_road.png", 50, 300, 1));
  speedToggles->addItem(new CValueControl("AutoNaviSpeedCtrlEnd", tr("SpeedCameraDecelEnd(6s)"), tr("Sets the deceleration completion point. A larger value completes deceleration farther away from the camera."), "../assets/offroad/icon_road.png", 3, 20, 1));
  speedToggles->addItem(new CValueControl("AutoNaviSpeedCtrlMode", tr("NaviSpeedControlMode(2)"), tr("0:No slowdown, 1: speed camera, 2: + accident prevention bump, 3: + mobile camera"), "../assets/offroad/icon_road.png", 0, 3, 1));
  speedToggles->addItem(new CValueControl("AutoNaviSpeedDecelRate", tr("SpeedCameraDecelRatex0.01m/s^2(80)"), tr("Lower number, slows down from a greater distance"), "../assets/offroad/icon_road.png", 10, 200, 10));
  speedToggles->addItem(new CValueControl("AutoNaviSpeedSafetyFactor", tr("SpeedCameraSafetyFactor(105%)"), "", "../assets/offroad/icon_road.png", 80, 120, 1));
  speedToggles->addItem(new CValueControl("AutoNaviSpeedBumpTime", tr("SpeedBumpTimeDistance(1s)"), "", "../assets/offroad/icon_road.png", 1, 50, 1));
  speedToggles->addItem(new CValueControl("AutoNaviSpeedBumpSpeed", tr("SpeedBumpSpeed(35Km/h)"), "", "../assets/offroad/icon_road.png", 10, 100, 5));
  speedToggles->addItem(new CValueControl("AutoRoadSpeedLimitOffset", tr("RoadSpeedLimitOffset(-1)"), tr("-1:NotUsed,RoadLimitSpeed+Offset"), "../assets/offroad/icon_road.png", -1, 100, 1));
  speedToggles->addItem(new CValueControl("AutoNaviCountDownMode", tr("NaviCountDown mode(2)"), tr("0: off, 1:tbt+camera, 2:tbt+camera+bump"), "../assets/offroad/icon_road.png", 0, 2, 1));
  speedToggles->addItem(new CValueControl("TurnSpeedControlMode", tr("Turn Speed control mode(1)"), tr("0: off, 1:vision, 2:vision+route, 3: route"), "../assets/offroad/icon_road.png", 0, 3, 1));
  speedToggles->addItem(new CValueControl("MapTurnSpeedFactor", tr("Map TurnSpeed Factor(100)"), "", "../assets/offroad/icon_map.png", 50, 300, 5));
  speedToggles->addItem(new CValueControl("AutoTurnControl", tr("ATC: Auto turn control(0)"), tr("0:None, 1: lane change, 2: lane change + speed, 3: speed"), "../assets/offroad/icon_road.png", 0, 3, 1));
  speedToggles->addItem(new CValueControl("AutoTurnControlSpeedTurn", tr("ATC: Turn Speed (20)"), tr("0:None, turn speed"), "../assets/offroad/icon_road.png", 0, 100, 5));
  speedToggles->addItem(new CValueControl("AutoTurnControlTurnEnd", tr("ATC: Turn CtrlDistTime (6)"), tr("dist=speed*time"), "../assets/offroad/icon_road.png", 0, 30, 1));
  speedToggles->addItem(new CValueControl("AutoRoadSpeedAdjust", tr("Auto Roadlimit Speed adjust (50%)"), "", "../assets/offroad/icon_road.png", -1, 100, 5));
  speedToggles->addItem(new CValueControl("AutoTurnMapChange", tr("ATC Auto Map Change(0)"), "", "../assets/offroad/icon_road.png", 0, 1, 1));

  toggles_layout->addWidget(cruiseToggles);
  toggles_layout->addWidget(latLongToggles);
  toggles_layout->addWidget(dispToggles);
  toggles_layout->addWidget(pathToggles);
  toggles_layout->addWidget(startToggles);
  toggles_layout->addWidget(speedToggles);
  ScrollView* toggles_view = new ScrollView(toggles, this);
  carrotLayout->addWidget(toggles_view, 1);

  homeScreen->setLayout(carrotLayout);
  main_layout->addWidget(homeScreen);
  main_layout->setCurrentWidget(homeScreen);

  togglesCarrot(0);
}

void CarrotPanel::togglesCarrot(int widgetIndex) {
  startToggles->setVisible(widgetIndex == 0);
  cruiseToggles->setVisible(widgetIndex == 1);
  speedToggles->setVisible(widgetIndex == 2);
  latLongToggles->setVisible(widgetIndex == 3);
  dispToggles->setVisible(widgetIndex == 4);
  pathToggles->setVisible(widgetIndex == 5);
}

void CarrotPanel::updateButtonStyles() {
  QString styleSheet = R"(
      #start_btn, #cruise_btn, #speed_btn, #latLong_btn ,#disp_btn, #path_btn {
          height: 120px; border-radius: 15px; background-color: #393939;
      }
      #start_btn:pressed, #cruise_btn:pressed, #speed_btn:pressed, #latLong_btn:pressed, #disp_btn:pressed, #path_btn:pressed {
          background-color: #4a4a4a;
      }
  )";

  switch (currentCarrotIndex) {
  case 0:
      styleSheet += "#start_btn { background-color: #33ab4c; }";
      break;
  case 1:
      styleSheet += "#cruise_btn { background-color: #33ab4c; }";
      break;
  case 2:
      styleSheet += "#speed_btn { background-color: #33ab4c; }";
      break;
  case 3:
      styleSheet += "#latLong_btn { background-color: #33ab4c; }";
      break;
  case 4:
      styleSheet += "#disp_btn { background-color: #33ab4c; }";
      break;
  case 5:
      styleSheet += "#path_btn { background-color: #33ab4c; }";
      break;
  }

  setStyleSheet(styleSheet);
}


CValueControl::CValueControl(const QString& params, const QString& title, const QString& desc, const QString& icon, int min, int max, int unit)
    : AbstractControl(title, desc, icon), m_params(params), m_min(min), m_max(max), m_unit(unit) {

    label.setAlignment(Qt::AlignVCenter | Qt::AlignRight);
    label.setStyleSheet("color: #e0e879");
    hlayout->addWidget(&label);

    QString btnStyle = R"(
      QPushButton {
        padding: 0;
        border-radius: 50px;
        font-size: 35px;
        font-weight: 500;
        color: #E4E4E4;
        background-color: #393939;
      }
      QPushButton:pressed {
        background-color: #4a4a4a;
      }
    )";

    btnminus.setStyleSheet(btnStyle);
    btnplus.setStyleSheet(btnStyle);
    btnminus.setFixedSize(150, 100);
    btnplus.setFixedSize(150, 100);
    btnminus.setText("－");
    btnplus.setText("＋");
    hlayout->addWidget(&btnminus);
    hlayout->addWidget(&btnplus);

    connect(&btnminus, &QPushButton::released, this, &CValueControl::decreaseValue);
    connect(&btnplus, &QPushButton::released, this, &CValueControl::increaseValue);

    refresh();
}

void CValueControl::showEvent(QShowEvent* event) {
    AbstractControl::showEvent(event);
    refresh();
}

void CValueControl::refresh() {
    label.setText(QString::fromStdString(Params().get(m_params.toStdString())));
}

void CValueControl::adjustValue(int delta) {
    int value = QString::fromStdString(Params().get(m_params.toStdString())).toInt();
    value = qBound(m_min, value + delta, m_max);
    Params().putInt(m_params.toStdString(), value);
    refresh();
}

void CValueControl::increaseValue() {
    adjustValue(m_unit);
}

void CValueControl::decreaseValue() {
    adjustValue(-m_unit);
}
