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

#include "selfdrive/ui/qt/offroad/model_selector.h"

// Define style constants to improve maintainability
namespace {
    const QString SELECTOR_BTN_STYLE = "background-color: #00309a; font-size: 48px;";
    const QString MODEL_LIST_STYLE = "font-size: 64px;";
    const QString SCROLLBAR_STYLE = "width: 96px;";
    const QString GROUP_HEADER_BG_COLOR = "#c8c8c8"; // Light gray
    const QString GROUP_HEADER_TEXT_COLOR = "#000000"; // Black

    // Role for storing the actual model name without indentation
    const int ModelNameRole = Qt::UserRole;
}

ModelSelector::ModelSelector(QWidget *parent) : QWidget(parent) {
    setupUI();
    setupModelListPanel();
    connectSignals();
}

QWidget* ModelSelector::setupUI() {
    QVBoxLayout* main_layout = new QVBoxLayout(this);
    main_layout->addSpacing(10);

    // Selector button
    QWidget* model_selector_btn_widget = new QWidget;
    QHBoxLayout* model_selector_btn_layout = new QHBoxLayout();
    QLabel* vehicle_model_label = new QLabel(tr("Vehicle Model:"));
    vehicle_model_label->setStyleSheet("margin-right: 2px; font-size: 48px;");
    model_selector_btn_layout->addWidget(vehicle_model_label);

    QString model_selected = QString::fromUtf8(Params().get("dp_device_model_selected").c_str());
    model_selector_btn = new QPushButton(model_selected.isEmpty() ? tr("[AUTO DETECT]") : model_selected);
    model_selector_btn->setObjectName("ModelSelectorBtn");
    model_selector_btn->setStyleSheet(SELECTOR_BTN_STYLE);
    model_selector_btn_layout->addWidget(model_selector_btn);
    model_selector_btn_layout->setAlignment(Qt::AlignCenter);
    model_selector_btn_layout->setStretch(1, 1);

    model_selector_btn_widget->setLayout(model_selector_btn_layout);
    main_layout->addWidget(model_selector_btn_widget);
    main_layout->addSpacing(10);
    main_layout->addStretch(); // Add stretch to push everything to the top

    setLayout(main_layout);
    return model_selector_btn_widget;
}

void ModelSelector::setupModelListPanel() {
    // Create model list panel
    model_list_panel = new QWidget();
    QVBoxLayout* model_list_layout = new QVBoxLayout(model_list_panel);
    model_list_layout->setContentsMargins(50, 25, 50, 25);

    model_list = new QListWidget(model_list_panel);

    // Set styles using the constants
    QString listStyle = QString("QListWidget { %1 } QScrollBar:vertical { %2 }")
                        .arg(MODEL_LIST_STYLE)
                        .arg(SCROLLBAR_STYLE);
    model_list->setStyleSheet(listStyle);

    model_list->setFixedHeight(750);
    model_list_layout->addWidget(model_list);

    model_list_frame = new ScrollView(model_list_panel, nullptr);
}

void ModelSelector::loadModelList() {
    if (model_list->count() > 0) {
        // If list is already populated, just update the selection
        updateCurrentSelection();
        return;
    }

    // Add auto-detect option
    QListWidgetItem* autoDetectItem = new QListWidgetItem(tr("[AUTO DETECT]"));
    autoDetectItem->setData(ModelNameRole, tr("[AUTO DETECT]"));
    model_list->addItem(autoDetectItem);

    Params params;
    QString model_list_str = QString::fromStdString(params.get("dp_device_model_list"));

    QJsonDocument document = QJsonDocument::fromJson(model_list_str.toUtf8());
    if (document.isArray()) {
        QJsonArray models = document.array();

        for (const auto& groupValue : models) {
            QJsonObject group = groupValue.toObject();
            QString groupName = group["group"].toString();

            // Add group header item
            QListWidgetItem* groupHeader = new QListWidgetItem(groupName);
            groupHeader->setFlags(Qt::NoItemFlags); // Make non-selectable
            groupHeader->setBackground(QColor(GROUP_HEADER_BG_COLOR));
            groupHeader->setForeground(QColor(GROUP_HEADER_TEXT_COLOR));
            groupHeader->setTextAlignment(Qt::AlignCenter);
            model_list->addItem(groupHeader);

            // Add models in this group
            QJsonArray groupModels = group["models"].toArray();
            for (const auto& model : groupModels) {
                QString modelName = model.toString();
                // Create item with visual indentation
                QListWidgetItem* modelItem = new QListWidgetItem("  " + modelName);
                // Store actual model name without indentation in user role
                modelItem->setData(ModelNameRole, modelName);
                model_list->addItem(modelItem);
            }
        }
    }

    // Set the current selection after loading
    updateCurrentSelection();
}

// New helper method to update the selection
void ModelSelector::updateCurrentSelection() {
    // Get the currently selected model from params
    Params params;
    QString currentModel = QString::fromStdString(params.get("dp_device_model_selected"));

    // If empty, select the AUTO DETECT option
    if (currentModel.isEmpty()) {
        model_list->setCurrentRow(0); // AUTO DETECT is the first item
        return;
    }

    // Otherwise, find and select the matching model
    for (int i = 0; i < model_list->count(); i++) {
        QListWidgetItem* item = model_list->item(i);
        // Only check selectable items (not group headers)
        if (item->flags() & Qt::ItemIsSelectable) {
            QString modelName = item->data(ModelNameRole).toString();
            if (modelName == currentModel) {
                model_list->setCurrentItem(item);
                break;
            }
        }
    }
}

void ModelSelector::clearModelList() {
    model_list->clear();
}

void ModelSelector::updateButtonText(const QString& text) {
    model_selector_btn->setText(text);
}

QWidget* ModelSelector::getModelListPanel() {
    return model_list_frame;
}

void ModelSelector::setPanelWidget(QStackedWidget* panel) {
    panel_widget = panel;
    if (panel_widget && model_list_frame->parent() != panel_widget) {
        model_list_frame->setParent(panel_widget);
        panel_widget->addWidget(model_list_frame);
    }
}

void ModelSelector::setNavButtonGroup(QButtonGroup* buttons) {
    nav_btns = buttons;
}

void ModelSelector::connectSignals() {
    connect(model_selector_btn, &QPushButton::clicked, [this]() {
        if (panel_widget) {
            // Load the model list when needed
            loadModelList();
            panel_widget->setCurrentWidget(model_list_frame);
        }
        emit buttonClicked();
    });

    connect(model_list, &QListWidget::itemClicked, [this](QListWidgetItem* item) {
        // Only process clicks on selectable items (not group headers)
        if (item->flags() & Qt::ItemIsSelectable) {
            // Get model name from the data role rather than trimming text
            QString model_name = item->data(ModelNameRole).toString();
            QString param_value = (model_name == tr("[AUTO DETECT]")) ? QString() : model_name;

            // Update param and button text
            Params().put("dp_device_model_selected", param_value.toStdString());
            updateButtonText(param_value.isEmpty() ? tr("[AUTO DETECT]") : model_name);

            // Emit signal that model was selected
            emit modelSelected(model_name);

            // Go back to the previous panel
            if (nav_btns && nav_btns->checkedButton()) {
                nav_btns->checkedButton()->click();
            } else if (nav_btns && nav_btns->buttons().size() > 0) {
                // Default to first panel if none selected
                nav_btns->buttons().first()->click();
            }
        }
    });

    if (model_list_frame) {
        model_list_frame->installEventFilter(this);
    }
}


bool ModelSelector::eventFilter(QObject *obj, QEvent *event) {
    if (obj == model_list_frame) {
        if (event->type() == QEvent::Hide) {
            clearModelList();
        }
    }
    return QWidget::eventFilter(obj, event);
}
