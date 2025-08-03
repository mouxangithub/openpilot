/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#include "selfdrive/ui/sunnypilot/qt/offroad/settings/longitudinal_panel.h"

LongitudinalPanel::LongitudinalPanel(QWidget *parent) : QWidget(parent) {
  setStyleSheet(R"(
    #back_btn {
      font-size: 50px;
      margin: 0px;
      padding: 15px;
      border-width: 0;
      border-radius: 30px;
      color: #dddddd;
      background-color: #393939;
    }
    #back_btn:pressed {
      background-color:  #4a4a4a;
    }
  )");

  main_layout = new QStackedLayout(this);
  ListWidget *list = new ListWidget(this, false);

  cruisePanelScreen = new QWidget(this);
  QVBoxLayout *vlayout = new QVBoxLayout(cruisePanelScreen);
  vlayout->setContentsMargins(0, 0, 0, 0);

  cruisePanelScroller = new ScrollViewSP(list, this);
  vlayout->addWidget(cruisePanelScroller);

  customAccIncrement = new CustomAccIncrement("CustomAccIncrementsEnabled", tr("Custom ACC Speed Increments"), "", "", this);
  list->addItem(customAccIncrement);

  QObject::connect(uiState(), &UIState::offroadTransition, this, &LongitudinalPanel::refresh);

  // chill to experimental transition control
  accToE2ETransitionControl = new ParamControlSP("BlendAccToE2ETransition",
    tr("Blend chill to experimental mode transition"),
    tr("Enable to blend braking desires when switching from chill to experimental in a smoother, more natural way. "
      "This allows for a gradual transition when switching from ACC to E2E longitudinal control."),
    "../assets/offroad/icon_shell.png", nullptr, true);
  // accToE2ETransitionControl->showDescription();
  list->addItem(accToE2ETransitionControl);

  // Vibe Personality Controller
  vibePersonalityControl = new ParamControlSP("VibePersonalityEnabled",
    tr("Vibe Personality Controller"),
    tr("Advanced driving personality system with separate controls for acceleration behavior (Eco/Normal/Sport) and following distance/braking (Relaxed/Standard/Aggressive). "
      "Customize your driving experience with independent acceleration and distance personalities."),
    "../assets/offroad/icon_shell.png");
  list->addItem(vibePersonalityControl);

  connect(vibePersonalityControl, &ParamControlSP::toggleFlipped, [=]() {
    refresh(offroad);
  });

  // Vibe Acceleration Personality
  vibeAccelPersonalityControl = new ParamControlSP("VibeAccelPersonalityEnabled",
    tr("Acceleration Personality"),
    tr("Controls acceleration behavior: Eco (efficient), Normal (balanced), Sport (responsive). "
      "Adjust how aggressively the vehicle accelerates while maintaining smooth operation."),
    "../assets/offroad/icon_shell.png");
  list->addItem(vibeAccelPersonalityControl);

  // Vibe Following Distance Personality
  vibeFollowPersonalityControl = new ParamControlSP("VibeFollowPersonalityEnabled",
    tr("Following Distance Personality"),
    tr("Controls following distance and braking behavior: Relaxed (longer distance, gentler braking), Standard (balanced), Aggressive (shorter distance, firmer braking). "
      "Fine-tune your comfort level in traffic situations."),
    "../assets/offroad/icon_shell.png");
  list->addItem(vibeFollowPersonalityControl);

  slcControl = new SpeedLimitControl(
    "SpeedLimitControl",
    tr("Speed Limit Control (SLC)"),
    tr("When you engage ACC, you will be prompted to set the cruising speed to the speed limit of the road adjusted by the Offset and Source Policy specified, or the current driving speed. "
      "The maximum cruising speed will always be the MAX set speed."),
    "",
    this);
  list->addItem(slcControl);

  connect(slcControl, &SpeedLimitControl::slcSettingsButtonClicked, [=]() {
    cruisePanelScroller->setLastScrollPosition();
    main_layout->setCurrentWidget(slcScreen);
  });

  slcScreen = new SpeedLimitControlSubpanel(this);
  connect(slcScreen, &SpeedLimitControlSubpanel::backPress, [=]() {
    cruisePanelScroller->restoreScrollPosition();
    main_layout->setCurrentWidget(cruisePanelScreen);
  });
  visionTurnSpeedControl = new ParamControlSP("VisionTurnSpeedControl",
    tr("Vision Turn Speed Controller"),
    tr("Also known as V-TSC, this controller automatically slows down for curvature while OP longitudinal is engaged."),
    "../assets/offroad/icon_shell.png");
  list->addItem(visionTurnSpeedControl);

  main_layout->addWidget(cruisePanelScreen);
  main_layout->addWidget(slcScreen);
  main_layout->setCurrentWidget(cruisePanelScreen);
  refresh(offroad);
}

void LongitudinalPanel::showEvent(QShowEvent *event) {
  main_layout->setCurrentWidget(cruisePanelScreen);
  refresh(offroad);
}

void LongitudinalPanel::refresh(bool _offroad) {
  auto cp_bytes = params.get("CarParamsPersistent");
  if (!cp_bytes.empty()) {
    AlignedBuffer aligned_buf;
    capnp::FlatArrayMessageReader cmsg(aligned_buf.align(cp_bytes.data(), cp_bytes.size()));
    cereal::CarParams::Reader CP = cmsg.getRoot<cereal::CarParams>();

    has_longitudinal_control = hasLongitudinalControl(CP);
    is_pcm_cruise = CP.getPcmCruise();
  } else {
    has_longitudinal_control = false;
    is_pcm_cruise = false;
  }

  QString accEnabledDescription = tr("Enable custom Short & Long press increments for cruise speed increase/decrease.");
  QString accNoLongDescription = tr("This feature can only be used with openpilot longitudinal control enabled.");
  QString accPcmCruiseDisabledDescription = tr("This feature is not supported on this platform due to vehicle limitations.");
  QString onroadOnlyDescription = tr("Start the vehicle to check vehicle compatibility.");

  if (offroad) {
    customAccIncrement->setDescription(onroadOnlyDescription);
    // customAccIncrement->showDescription();
  } else {
    if (has_longitudinal_control) {
      if (is_pcm_cruise) {
        customAccIncrement->setDescription(accPcmCruiseDisabledDescription);
        // customAccIncrement->showDescription();
      } else {
        customAccIncrement->setDescription(accEnabledDescription);
      }
    } else {
      params.remove("CustomAccIncrementsEnabled");
      customAccIncrement->toggleFlipped(false);
      customAccIncrement->setDescription(accNoLongDescription);
      // customAccIncrement->showDescription();
    }
  }
  bool vibePersonalityEnabled = params.getBool("VibePersonalityEnabled");
  if (vibePersonalityEnabled) {
    vibeAccelPersonalityControl->setVisible(true);
    vibeFollowPersonalityControl->setVisible(true);
  } else {
    vibeAccelPersonalityControl->setVisible(false);
    vibeFollowPersonalityControl->setVisible(false);
  }

  // enable toggle when long is available and is not PCM cruise
  customAccIncrement->setEnabled(has_longitudinal_control && !is_pcm_cruise && !offroad);
  customAccIncrement->refresh();

  // Vibe Personality controls - always enabled for toggling
  vibePersonalityControl->setEnabled(true);
  vibeAccelPersonalityControl->setEnabled(true);
  vibeFollowPersonalityControl->setEnabled(true);
  vibePersonalityControl->refresh();
  vibeAccelPersonalityControl->refresh();
  vibeFollowPersonalityControl->refresh();

  offroad = _offroad;
}
