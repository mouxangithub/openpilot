/*
Copyright (c) 2025 Rick Lan

This software is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).
You are free to share and adapt this work for non-commercial purposes, provided you give appropriate credit and distribute any modifications under the same license.

To view a copy of this license, visit:
http://creativecommons.org/licenses/by-nc-sa/4.0/

---

**Commercial Licensing:**
Use of this software for commercial purposes is strictly prohibited without a separate, paid license.
To purchase a commercial license, please contact ricklan@gmail.com.
*/

#pragma once

#include <QWidget>
#include <QPushButton>
#include <QListWidget>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QListWidgetItem>
#include <QDebug>
#include <QStackedWidget>
#include <QButtonGroup>  // Add this include for QButtonGroup
#include <QEvent>
#include "common/params.h"
#include "selfdrive/ui/qt/widgets/scrollview.h"

class ModelSelector : public QWidget {
    Q_OBJECT

public:
    explicit ModelSelector(QWidget *parent = nullptr);

    // Get the model list panel widget
    QWidget* getModelListPanel();

    // Set the panel widget to switch to when selecting models
    void setPanelWidget(QStackedWidget* panel);

    // Set the button group to return to after model selection
    void setNavButtonGroup(QButtonGroup* nav_btns);

signals:
    void buttonClicked();
    void modelSelected(const QString& model_name);

private:
    QPushButton* model_selector_btn;
    QListWidget* model_list;
    QWidget* model_list_panel;
    ScrollView* model_list_frame;
    QStackedWidget* panel_widget = nullptr;
    QButtonGroup* nav_btns = nullptr;

    QWidget* setupUI();
    void setupModelListPanel();
    void loadModelList();
    void updateCurrentSelection();
    void clearModelList();
    void connectSignals();
    void updateButtonText(const QString& text);

protected:
    bool eventFilter(QObject *obj, QEvent *event) override;
};
