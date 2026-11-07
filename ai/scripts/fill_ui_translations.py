#!/usr/bin/env python3
"""Fill missing zh-CHS / zh-CHT translations in the UI .po files.

Windows has no zmq/zstandard here, so update_translations.py (which imports
multilang -> swaglog) cannot re-extract; the .po files already carry every
entry update_translations.py merged on the device, so only the msgstr values
are filled. parse_po/write_po round-trip is byte-identical, so untouched
entries keep their exact formatting.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
from openpilot.selfdrive.ui.translations.potools import parse_po, write_po  # noqa: E402

CHS = {
  # --- model download mirror (this fork's own rows) ---
  "Model Download Mirror": "模型下载镜像",
  "Model List Source": "模型列表来源",
  "Mirror": "镜像",
  "Direct": "直连",
  "Custom": "自定义",
  "Proxy": "代理",
  "Current": "当前",
  "ready on Jetson": "已在 Jetson 构建",
  "Custom Mirror": "自定义镜像",
  "Catalog Proxy Prefix": "列表代理前缀",
  "Base URL replacing https://huggingface.co, e.g. https://hf-mirror.com":
    "替换 https://huggingface.co 的基础地址，例如 https://hf-mirror.com",
  "Prefix prepended to the catalog URL, e.g. https://gh-proxy.com":
    "前缀会加在列表 URL 之前，例如 https://gh-proxy.com",
  "The mirror must be an http(s) URL without spaces, e.g. https://hf-mirror.com":
    "镜像必须是不含空格的 http(s) URL，例如 https://hf-mirror.com",
  "The proxy must be an http(s) URL without spaces, e.g. https://gh-proxy.com":
    "代理必须是不含空格的 http(s) URL，例如 https://gh-proxy.com",
  "huggingface.co is unreachable on many networks. Mirror sends model downloads to a mirror site instead; ":
    "huggingface.co 在不少网络下无法访问。镜像会把模型下载改走镜像站；",
  "Direct uses huggingface.co as-is; Custom lets you enter your own mirror. Applies to the next download.":
    "直连按原样使用 huggingface.co；自定义可填入你自己的镜像。对下一次下载生效。",
  "The model list lives on GitHub raw. Auto tries direct first and falls back to a CDN mirror when it fails; ":
    "模型列表托管在 GitHub raw 上。自动会先尝试直连，失败时回退到 CDN 镜像；",
  "Direct never falls back; Proxy always fetches through your own prefix. Press Refresh Model List to apply.":
    "直连不会回退；代理始终通过你自己的前缀获取。按下“刷新模型列表”后生效。",
  # --- jetlink / big model status ---
  "Jetlink connected:": "Jetlink 已连接：",
  "check cable": "检查线缆",
  "check cable or app": "检查线缆或手机 App",
  "{}, {} ({} drops)": "{}, {}（{} 次掉线）",
  "{} day ago": "{} 天前",
  "{} hour ago": "{} 小时前",
  "{} minute ago": "{} 分钟前",
  "{} ALERT": "{} 警告",
  "{} segment of your driving is in the training dataset so far.": "目前已有 {} 段行车数据进入训练集。",
  # --- external cluster HUD ---
  "Master switch for the external cluster HUD renderer.": "外接仪表 HUD 渲染的总开关。",
  "Draw radar tracks on the external cluster.": "在外接仪表上绘制雷达目标轨迹。",
  "Enable the cluster map HUD profile overlay.": "启用外接仪表地图 HUD 的 profile 叠加。",
  "Mirror the external cluster display horizontally.": "水平镜像外接仪表显示。",
  "Show debug overlays on the external cluster.": "在外接仪表上显示调试叠加层。",
  "Refresh rate of the external cluster map, in frames per second.": "外接仪表地图的刷新率，单位为帧/秒。",
  "Ego Bottom": "主车居下",
  "Road Camera": "前视摄像头",
  "Wide Camera": "广角摄像头",
  "Auto Camera": "自动选择摄像头",
  "Driving Left": "靠左行驶",
  "Driving Right": "靠右行驶",
  # --- radar / vehicle ---
  "Color radar tracks by their detection source.": "按检测来源为雷达轨迹着色。",
  "Speed at which cruise set speed is re-synchronized. Tesla BYD only.": "巡航设定速度重新同步的速度阈值。仅限特斯拉、比亚迪。",
  "BYD only: feed corner-radar tracks into the radar interface.": "仅比亚迪：把角雷达轨迹输入雷达接口。",
  "Synthesises a camera distance when the car sends only an enforcement speed. 0.1 s units; 60 = 6.0 s.":
    "当车辆只发送执法测速值时的合成摄像头距离。单位为 0.1 秒；60 = 6.0 秒。",
  "1 = take the ACC set speed from the car (PCM). Required on Toyota: its PCM consumes the +/- buttons itself, so openpilot would otherwise keep its own set speed while the cluster moves.":
    "1 = 从车辆（PCM）获取 ACC 设定速度。丰田上必须开启：其 PCM 会自行处理 +/- 按键，否则仪表变化时 openpilot 仍会保留自己的设定速度。",
  # --- misc / enums ---
  "All Speeds": "所有速度",
  "All Speeds + Distance": "所有速度 + 距离",
  "Speed + Distance": "速度 + 距离",
  "Trip Report": "行程报告",
  "Battery": "电量",
  "Linear": "线性",
  "Auto": "自动",
  "JPEG": "JPEG",
  "Stop": "停车",
  "ON": "开",
  "Dark": "深色",
  "Light": "浅色",
  "Debug": "调试",
  "Debug Graph": "调试曲线",
  "Debug Graph Right": "调试曲线（右）",
  "Debug System": "调试系统",
  "Vehicle Speed": "车速",
  "Hardware H.264": "硬件 H.264",
  "Software H.264": "软件 H.264",
  "Testimg...": "",
  "Testing...": "测试中…",
  "Paired devices": "已配对设备",
  "Tap a cell to cycle actions, then Save.": "点按单元格循环切换动作，然后保存。",
  "Generic keyboard / HID": "通用键盘 / HID",
  "Yiser-J6": "Yiser-J6",
  # the Wi-Fi link (zoompilot wifi-lossless)
  "Join the device's hotspot and open Jetlink there.": "请接入手机热点，并在手机上打开 Jetlink。",
  "Run big models over a connected device running Jetlink. USB and iOS turn off ADB.":
    "在已连接的外接算力上运行大模型。USB 与 iOS 模式会关闭 ADB。",
  "check Wi-Fi or app": "请检查 Wi-Fi 或手机 App",
}
CHS.pop("Testimg...", None)

CHT = {
  # --- model download mirror (this fork's own rows) ---
  "Model Download Mirror": "模型下載鏡像",
  "Model List Source": "模型列表來源",
  "Mirror": "鏡像",
  "Direct": "直連",
  "Custom": "自訂",
  "Proxy": "代理",
  "Current": "目前",
  "ready on Jetson": "已在 Jetson 建置",
  "Custom Mirror": "自訂鏡像",
  "Catalog Proxy Prefix": "列表代理前綴",
  "Base URL replacing https://huggingface.co, e.g. https://hf-mirror.com":
    "取代 https://huggingface.co 的基礎網址，例如 https://hf-mirror.com",
  "Prefix prepended to the catalog URL, e.g. https://gh-proxy.com":
    "前綴會加在列表 URL 之前，例如 https://gh-proxy.com",
  "The mirror must be an http(s) URL without spaces, e.g. https://hf-mirror.com":
    "鏡像必須是不含空格的 http(s) URL，例如 https://hf-mirror.com",
  "The proxy must be an http(s) URL without spaces, e.g. https://gh-proxy.com":
    "代理必須是不含空格的 http(s) URL，例如 https://gh-proxy.com",
  "huggingface.co is unreachable on many networks. Mirror sends model downloads to a mirror site instead; ":
    "huggingface.co 在不少網路下無法連線。鏡像會把模型下載改走鏡像站；",
  "Direct uses huggingface.co as-is; Custom lets you enter your own mirror. Applies to the next download.":
    "直連依原樣使用 huggingface.co；自訂可填入你自己的鏡像。對下一次下載生效。",
  "The model list lives on GitHub raw. Auto tries direct first and falls back to a CDN mirror when it fails; ":
    "模型列表託管在 GitHub raw 上。自動會先嘗試直連，失敗時回退到 CDN 鏡像；",
  "Direct never falls back; Proxy always fetches through your own prefix. Press Refresh Model List to apply.":
    "直連不會回退；代理一律透過你自己的前綴取得。按下「重新整理模型列表」後生效。",
  # --- jetlink / big model status ---
  "Jetlink connected:": "Jetlink 已連線：",
  "check cable": "檢查線材",
  "check cable or app": "檢查線材或手機 App",
  "{}, {} ({} drops)": "{}, {}（{} 次斷線）",
  "{} day ago": "{} 天前",
  "{} hour ago": "{} 小時前",
  "{} minute ago": "{} 分鐘前",
  "{} ALERT": "{} 警告",
  "{} segment of your driving is in the training dataset so far.": "目前已有 {} 段行車資料進入訓練集。",
  # --- external cluster HUD ---
  "Master switch for the external cluster HUD renderer.": "外接儀表 HUD 渲染的總開關。",
  "Draw radar tracks on the external cluster.": "在外接儀表上繪製雷達目標軌跡。",
  "Enable the cluster map HUD profile overlay.": "啟用外接儀表地圖 HUD 的 profile 疊加。",
  "Mirror the external cluster display horizontally.": "水平鏡像外接儀表顯示。",
  "Show debug overlays on the external cluster.": "在外接儀表上顯示除錯疊加層。",
  "Refresh rate of the external cluster map, in frames per second.": "外接儀表地圖的更新率，單位為幀/秒。",
  "Ego Bottom": "主車居下",
  "Road Camera": "前視相機",
  "Wide Camera": "廣角相機",
  "Auto Camera": "自動選擇相機",
  "Driving Left": "靠左行駛",
  "Driving Right": "靠右行駛",
  # --- radar / vehicle ---
  "Color radar tracks by their detection source.": "依偵測來源為雷達軌跡著色。",
  "Speed at which cruise set speed is re-synchronized. Tesla BYD only.": "巡航設定速度重新同步的速度門檻。僅限特斯拉、比亞迪。",
  "BYD only: feed corner-radar tracks into the radar interface.": "僅比亞迪：把角雷達軌跡輸入雷達介面。",
  "Synthesises a camera distance when the car sends only an enforcement speed. 0.1 s units; 60 = 6.0 s.":
    "當車輛只送出執法測速值時的合成相機距離。單位為 0.1 秒；60 = 6.0 秒。",
  "1 = take the ACC set speed from the car (PCM). Required on Toyota: its PCM consumes the +/- buttons itself, so openpilot would otherwise keep its own set speed while the cluster moves.":
    "1 = 從車輛（PCM）取得 ACC 設定速度。豐田上必須開啟：其 PCM 會自行處理 +/- 按鍵，否則儀表變化時 openpilot 仍會保留自己的設定速度。",
  # --- misc / enums ---
  "All Speeds": "所有速度",
  "All Speeds + Distance": "所有速度 + 距離",
  "Speed + Distance": "速度 + 距離",
  "Trip Report": "行程報告",
  "Battery": "電量",
  "Linear": "線性",
  "Auto": "自動",
  "JPEG": "JPEG",
  "Stop": "停車",
  "ON": "開",
  "Dark": "深色",
  "Light": "淺色",
  "Debug": "除錯",
  "Debug Graph": "除錯曲線",
  "Debug Graph Right": "除錯曲線（右）",
  "Debug System": "除錯系統",
  "Vehicle Speed": "車速",
  "Hardware H.264": "硬體 H.264",
  "Software H.264": "軟體 H.264",
  "Testing...": "測試中…",
  "Paired devices": "已配對裝置",
  "Tap a cell to cycle actions, then Save.": "點按儲存格循環切換動作，然後儲存。",
  "Generic keyboard / HID": "通用鍵盤 / HID",
  "Yiser-J6": "Yiser-J6",
  # the Wi-Fi link (zoompilot wifi-lossless)
  "Join the device's hotspot and open Jetlink there.": "請接入手機熱點，並在手機上開啟 Jetlink。",
  "Run big models over a connected device running Jetlink. USB and iOS turn off ADB.":
    "在已連接的外接算力上執行大模型。USB 與 iOS 模式會關閉 ADB。",
  "check Wi-Fi or app": "請檢查 Wi-Fi 或手機 App",
}

# CHT-only extras: the traditional file has never been fully populated.
CHT.update({
  "1. sunnypilot is a driver assistance system.": "1. sunnypilot 是駕駛輔助系統。",
  "2. You must pay attention at all times.": "2. 您必須全程保持專注。",
  "3. You must be ready to take over at any time.": "3. 您必須隨時準備接管車輛。",
  "4. You are fully responsible for driving the car.": "4. 駕駛車輛的責任完全由您承擔。",
  "3-Finger": "三指",
  "4-Finger": "四指",
  "5-Finger": "五指",
  "ACTIVE": "已啟用",
  "Acceleration Change Cost": "加速度變化代價",
  "Acceleration Profile": "加速曲線",
  "All provinces": "所有省份",
  "An operating system update is required. Connect your device to Wi-Fi for the fastest update experience. The download size is approximately 1GB.":
    "需要更新作業系統。將裝置連上 Wi-Fi 可獲得最快的更新體驗。下載大小約為 1GB。",
  "Any fast phone or laptop charger should be fine.": "任何快速的手機或筆電充電器都可以。",
  "Available devices": "可用裝置",
  "Backing up {progress}%": "備份中 {progress}%",
  "Bluetooth UART not available": "藍牙 UART 無法使用",
  "Bluetooth UART not exposed by this AGNOS kernel": "此 AGNOS 核心未開放藍牙 UART",
  "Bluetooth is not installed": "未安裝藍牙",
  "Bluetooth power node not detected": "未偵測到藍牙電源節點",
  "Bluetooth radio hardware not detected": "未偵測到藍牙無線電硬體",
  "Bluetooth service is stopped": "藍牙服務已停止",
  "CONFIGURE": "設定",
  "Cloud": "雲端",
  "Comfort Brake": "舒適煞車",
  'Confirm pairing with "{}"?': "確認與「{}」配對？",
  "Current State": "目前狀態",
  "Danger Zone Cost": "危險區域代價",
  "Description": "說明",
  "Device must be registered with the comma.ai backend to pair.": "裝置必須先註冊到 comma.ai 後端才能配對。",
  "Device name": "裝置名稱",
  "Distance Cost": "距離代價",
  "Do all of my segments get pulled in Firehose Mode?": "Firehose 模式會拉取我所有的行車段嗎？",
  "Does it matter how or where I drive?": "我怎麼開、在哪開有差別嗎？",
  "Does it matter which software I run?": "我使用哪套軟體有差別嗎？",
  "Driver camera unavailable": "駕駛監控相機無法使用",
  "Eco": "經濟",
  "Eco is gentlest, Normal balances a prompt start with smooth catch-up, and Sport is more responsive.":
    "經濟最溫和，標準在迅速起步與平順跟上之間取得平衡，運動則更靈敏。",
  'Enable "Always Offroad" in Device panel, or turn vehicle off to change.':
    "請在「裝置」面板啟用「永遠離路」，或熄火後再變更。",
  "Enable Accel Controller": "啟用加速度控制器",
  "Enable drive mode btn link": "啟用駕駛模式按鍵連動",
  "Enable enhanced blind-spot monitoring behavior for certain Prius TSS2 and TSS-P Toyotas.":
    "為部分 Prius TSS2 與 TSS-P 豐田車款啟用強化的盲點監控行為。",
  "Enter PIN": "輸入 PIN 碼",
  "Enter passkey": "輸入配對碼",
  "Enter this code in the sunnylink app on your phone.": "請在手機的 sunnylink App 中輸入此驗證碼。",
  "Failed to get available branches. Ensure you're connected to the internet and try again.":
    "無法取得可用分支。請確認已連上網際網路後再試。",
  "Flash an AGNOS with Bluetooth support or plug in a USB Bluetooth dongle.":
    "請刷入支援藍牙的 AGNOS，或插入 USB 藍牙接收器。",
  "Follow Time - Aggressive": "跟車時間 - 積極",
  "Follow Time - Relaxed": "跟車時間 - 從容",
  "Follow Time - Standard": "跟車時間 - 標準",
  "For maximum effectiveness, bring your device inside and connect to a good USB-C adapter and Wi-Fi weekly.\n\nFirehose Mode can also work while you're driving if connected to a hotspot or unlimited SIM card.":
    "為達到最佳效果，請每週將裝置帶回室內，接上良好的 USB-C 電源與 Wi-Fi。\n\n若連上熱點或不限流量 SIM 卡，Firehose 模式也能在行駛中使用。",
  'Forget "{}"?': "忘記「{}」？",
  "Frequently Asked Questions": "常見問題",
  "INACTIVE: connect to an unmetered network": "未啟用：請連上不計流量的網路",
  "If you'd like to proceed, use https://flash.comma.ai to restore your device to a factory state later.":
    "若您要繼續，日後可用 https://flash.comma.ai 將裝置還原至出廠狀態。",
  "Install BlueZ to enable Bluetooth HID remotes and device management.":
    "安裝 BlueZ 以啟用藍牙 HID 遙控器與裝置管理。",
  "Install Bluetooth": "安裝藍牙",
  "Installing...": "安裝中…",
  "Invalid URL: {url}": "無效的 URL：{url}",
  "It has not been tested by comma.": "它未經 comma 測試。",
  "It may cause damage to your device and/or vehicle.": "可能造成您的裝置及/或車輛損壞。",
  "It may not comply with relevant safety standards.": "可能不符合相關安全標準。",
  "Jerk Cost": "加加速度代價",
  "Lead Danger Factor": "前車危險係數",
  "Lets you choose how sunnypilot starts, catches up, and settles at the cruise speed. Emergency braking and stopping are unchanged.":
    "讓您選擇 sunnypilot 如何起步、跟上並穩定在巡航速度。緊急煞車與停車行為不變。",
  "Local": "本機",
  "MADS Screen Activation": "MADS 螢幕啟用方式",
  "MPH": "英里/時",
  "Manage the mobile app(s) connected over Wi-Fi: pair a new app ": "管理透過 Wi-Fi 連線的手機 App：配對新的 App ",
  "Name shown to other Bluetooth devices.": "顯示給其他藍牙裝置的名稱。",
  "No Bluetooth adapter found": "找不到藍牙介面卡",
  "No custom software found at this URL: {url}": "此 URL 找不到自訂軟體：{url}",
  "No devices found": "找不到裝置",
  "No eGPU (big model) is selected. The default model is running.": "未選擇 eGPU（大模型）。目前執行預設模型。",
  "No quality data": "無品質資料",
  "No, we selectively pull a subset of your segments.": "不會，我們只會選擇性拉取您部分的行車段。",
  "Nope, just drive as you normally would.": "不用，照您平常的方式開就好。",
  "Not set": "未設定",
  "Note: Setting this to Off will reset your MADS settings to default.": "注意：設為關閉會將您的 MADS 設定重設為預設值。",
  "Offline": "離線",
  "Only works above {speed} {unit}.": "僅在 {speed} {unit} 以上運作。",
  "Open a 5-minute pairing window and show the code to ": "開啟 5 分鐘的配對視窗，並將驗證碼顯示給 ",
  "Pair App": "配對 App",
  'Pair with "{}"?': "與「{}」配對？",
  "Pair with mobile app": "與手機 App 配對",
  "Pairing code: {}": "配對碼：{}",
  "Please connect to Wi-Fi to complete initial pairing.": "請連上 Wi-Fi 以完成初次配對。",
  "Please connect to Wi-Fi to update.": "請連上 Wi-Fi 以更新。",
  "Province": "省份",
  "Quality": "品質",
  "Remove all pairings and restart the Bluetooth service.": "移除所有配對並重新啟動藍牙服務。",
  "Reset Bluetooth": "重設藍牙",
  "Reset to Defaults": "重設為預設值",
  "Restoring {progress}%": "還原中 {progress}%",
  "Retry": "重試",
  "SSH keys": "SSH 金鑰",
  "Screen brightness when offroad. 0 uses the device default.": "離路時的螢幕亮度。0 代表使用裝置預設值。",
  "Select Country": "選擇國家",
  "Select Province": "選擇省份",
  "Select State": "選擇州/省",
  "Selecting a higher finger count may reduce accidental activations.": "選擇較多的手指數量可減少誤觸。",
  "Sharing your data with comma helps improve openpilot and sunnypilot for everyone.":
    "與 comma 分享您的資料，能協助改善所有人的 openpilot 與 sunnypilot。",
  "Sport": "運動",
  "Start the Bluetooth service to scan and pair devices.": "啟動藍牙服務以掃描並配對裝置。",
  "Status Details": "狀態詳細資料",
  "Stop Distance": "停車距離",
  "Sunnylink Local Connections": "Sunnylink 本機連線",
  "This AGNOS kernel does not expose /dev/ttyHS1. Reflash to a Bluetooth-capable AGNOS build.":
    "此 AGNOS 核心未開放 /dev/ttyHS1。請刷入支援藍牙的 AGNOS 版本。",
  "This allows the use of full MADS functionality when enabled.": "啟用後可使用完整的 MADS 功能。",
  "This device or AGNOS build lacks /dev/btpower.": "此裝置或 AGNOS 版本缺少 /dev/btpower。",
  "This device or AGNOS build lacks the required Bluetooth UART and power nodes.":
    "此裝置或 AGNOS 版本缺少所需的藍牙 UART 與電源節點。",
  "Toyota: Auto Brake Hold FOR TSS2 HYBRID CARS": "豐田：TSS2 油電車款的 Auto Brake Hold",
  "Toyota: Prius TSS2 BSM and some tssp": "豐田：Prius TSS2 BSM 與部分 TSS-P",
  "Toyota: custom longitudinal for TSS2": "豐田：TSS2 自訂縱向控制",
  "UNPAIR": "取消配對",
  "Unpair": "取消配對",
  "Use a custom longitudinal tuning profile for TSS2 Toyota vehicles.": "為 TSS2 豐田車款使用自訂縱向調校設定。",
  "Use a multi-finger press on the infotainment screen to toggle MADS.": "在車機螢幕上以多指點按來切換 MADS。",
  "Use caution when installing third-party software.": "安裝第三方軟體時請謹慎。",
  "Use the vehicle's auto brake hold feature on supported TSS2 hybrid Toyotas.":
    "在支援的 TSS2 油電豐田車款上使用車輛本身的 auto brake hold 功能。",
  "Waiting for the app…": "等待 App 中…",
  "Warning: May experience steering oscillations below {speed} {unit} during turns, recommend disabling this feature if you experience these.":
    "警告：在 {speed} {unit} 以下過彎時可能出現轉向震盪，若發生此情況建議停用本功能。",
  "What's a good USB-C adapter?": "什麼是好的 USB-C 充電器？",
  "Yes, only upstream openpilot (and particular forks) are able to be used for training.":
    "會，只有上游 openpilot（及特定分支）的資料能用於訓練。",
  "You must accept the Terms of Service to use sunnypilot.": "您必須接受服務條款才能使用 sunnypilot。",
  "You will need the pairing code again to reconnect it.": "重新連線時需要再次輸入配對碼。",
  "acceleration profile": "加速曲線",
  "accept\nterms": "接受\n條款",
  "aggressive": "積極",
  "allow data uploading": "允許上傳資料",
  "alpha longitudinal": "alpha 縱向控制",
  "always-on driver monitor": "常開駕駛監控",
  "apn settings": "APN 設定",
  "back": "返回",
  "branch": "分支",
  "cellular metered": "行動網路計量",
  "check for update": "檢查更新",
  "connected": "已連線",
  "connecting...": "連線中…",
  "decline &\nuninstall": "拒絕並\n卸載",
  "developer": "開發者",
  "device": "裝置",
  "distraction detection level": "分心偵測等級",
  "do you want to share video data for training?": "您要分享影片資料用於訓練嗎？",
  "driver camera data": "駕駛監控相機資料",
  "driving personality": "駕駛個性",
  "eGPU (Chestnut) not detected. Connect your eGPU hardware to enable.": "未偵測到 eGPU（Chestnut）。請連接您的 eGPU 硬體以啟用。",
  "eGPU Active": "eGPU 已啟用",
  "eGPU Available": "eGPU 可用",
  "eGPU Failed": "eGPU 失敗",
  "eGPU Loading...": "eGPU 載入中…",
  "eGPU Not Active": "eGPU 未啟用",
  "eGPU big model is being loaded. This may take a moment.": "eGPU 大模型正在載入。這可能需要一點時間。",
  "eGPU big model is running and healthy.": "eGPU 大模型運作正常。",
  "eGPU was selected but failed to start. Check device connection and model files.":
    "已選擇 eGPU 但啟動失敗。請檢查裝置連線與模型檔案。",
  "eco": "經濟",
  "edit": "編輯",
  "enable accel controller": "啟用加速度控制器",
  "enable roaming": "啟用漫遊",
  "enable sunnypilot": "啟用 sunnypilot",
  "enable tethering": "啟用網路共享",
  "enter APN...": "輸入 APN…",
  "enter GitHub username...": "輸入 GitHub 使用者名稱…",
  "enter password...": "輸入密碼…",
  "enter this code in the sunnylink app": "在 sunnylink App 中輸入此驗證碼",
  "exit": "結束",
  "experimental mode": "實驗模式",
  "firehose": "firehose",
  "forgetting...": "正在忘記…",
  "imu calibration": "IMU 校正",
  "joystick debug mode": "搖桿除錯模式",
  "lane departure warnings": "車道偏移警示",
  "lateral maneuver mode": "橫向操作模式",
  "lenient": "寬鬆",
  "longitudinal maneuver mode": "縱向操作模式",
  "moderate": "中等",
  "network": "網路",
  "network usage": "網路用量",
  "no alerts": "無警示",
  "no, don't upload": "不，不要上傳",
  "normal": "標準",
  "not in range": "超出範圍",
  "openpilot can't start\ncheck alerts": "openpilot 無法啟動\n請檢查警示",
  "or go to https://sunnypilot.ai/terms": "或前往 https://sunnypilot.ai/terms",
  "or unpair existing ones.": "或取消配對現有裝置。",
  "pair app": "配對 App",
  "pair with comma connect": "與 comma connect 配對",
  "pair with mobile app": "與手機 App 配對",
  "record & upload driver camera": "錄製並上傳駕駛監控相機",
  "record & upload mic audio": "錄製並上傳麥克風音訊",
  "relaxed": "從容",
  "road": "道路",
  "searching for networks": "正在搜尋網路",
  "slide to": "滑動以",
  "slide to forget": "滑動以忘記",
  "slide to unpair": "滑動以取消配對",
  "software": "軟體",
  "sport": "運動",
  "standard": "標準",
  "start the car to\nuse sunnypilot": "請發動車輛\n以使用 sunnypilot",
  "starting...": "啟動中…",
  "strict": "嚴格",
  "sunnylink enables secured remote access to your comma device from anywhere, including settings management, remote monitoring, real-time dashboard, etc.":
    "sunnylink 讓您隨時隨地安全地遠端存取 comma 裝置，包括設定管理、遠端監控、即時儀表板等。",
  "sunnylink is designed to be enabled as part of sunnypilot's core functionality. If sunnylink is disabled, features such as settings management, remote monitoring, real-time dashboards will be unavailable.":
    "sunnylink 設計為 sunnypilot 核心功能的一部分。若停用 sunnylink，設定管理、遠端監控、即時儀表板等功能將無法使用。",
  "sunnylink local": "sunnylink 本機",
  "swipe for QR code": "滑動顯示 QR code",
  "system booting": "系統啟動中",
  "target branch": "目標分支",
  "terms of\nservice": "服務\n條款",
  "tethering": "網路共享",
  "tethering password": "網路共享密碼",
  "this may take up to\na minute{dots}": "這可能需要\n一分鐘{dots}",
  "toggles": "切換開關",
  "type into the app. Closing the dialog cancels pairing.": "在 App 中輸入。關閉對話框會取消配對。",
  "ui debug mode": "UI 除錯模式",
  "uninstall": "卸載",
  "uninstall sunnypilot": "卸載 sunnypilot",
  "unsupported": "不支援",
  "use metric units": "使用公制單位",
  "version": "版本",
  "waiting for the app…": "等待 App 中…",
  "what is sunnypilot?": "什麼是 sunnypilot？",
  "wide": "廣角",
  "wrong password": "密碼錯誤",
  "{}% - Downloading Maps": "{}% - 下載地圖中",
})


def apply(lang: str, mapping: dict) -> int:
  path = Path("openpilot/selfdrive/ui/translations") / f"app_{lang}.po"
  header, entries = parse_po(path)
  used, n = set(), 0
  for e in entries:
    if (e.msgstr or "").strip():
      continue
    if e.msgid in mapping:
      e.msgstr = mapping[e.msgid]
      used.add(e.msgid)
      n += 1
  write_po(path, header, entries)
  unused = set(mapping) - used
  print(f"{lang}: filled {n}; unused map keys: {len(unused)}")
  for k in sorted(unused):
    print("   !", k[:110])
  return len(unused)


if __name__ == "__main__":
  apply("zh-CHS", CHS)
  apply("zh-CHT", CHT)
