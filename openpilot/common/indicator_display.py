"""Read-only, bounded automatic-indicator presentation shared by all displays.

cp 同名文件的移植：读取 /dev/shm/carrot-indicator-display.json（词表写入方见
selfdrived/indicator_layer.py 与外部 carrot 守护进程），只读、有界（1KB / 0.6s）。
"""
import json
import math
from pathlib import Path
import time

PATH = Path('/dev/shm/carrot-indicator-display.json')
MAX_BYTES = 1024
MAX_AGE = .6
ORIGINS = {'turn': 'TBT 转弯', 'lane': 'ATC 变道', 'tbt': '250m 右转',
           'manual': '驾驶员接近车道', 'model_path': '模型路径',
           'model_desire': '模型变道', 'model_turn': '模型转弯', 'bluetooth': '蓝牙遥控'}
REASONS = {'confirming': '条件确认中', 'approach': '接近转弯点', 'turning': '转弯进行中',
           'boundary': '接近车道边界', 'waiting_conditions': '等待车道与周边条件',
           'front': '等待前车距离与相对速度', 'bsd': '右侧 BSD 检测',
           'admission': '确认发送条件', 'inputs': '等待输入状态', 'peer': '等待接收设备',
           'completed': '已完成', 'returned': '已回到车道内', 'geometry': '车道位置不确定',
           'relabel': '车道线重标记', 'driver_opposite': '驾驶员反向转向',
           'driver': '驾驶员操作', 'driver_override': '驾驶员操作',
           'route_or_distance': '路径或距离条件结束', 'route': '路径条件结束',
           'timeout': '保持时间结束', 'cancelled': '请求结束', 'ended': '请求结束',
           'disabled': '功能关闭', 'start': '起始条件结束', 'atc': '其他 ATC 动作',
           'turn_started': '转弯已开始', 'maneuver': '变道条件结束',
           'interrupted': '变道中断', 'route_jump': '路径距离变化',
           'invalid': '输入无效', 'active': '保持中', 'waiting': '等待开始',
           'changing': '变道中', 'finishing': '变道收尾', 'trigger': '条件已满足'}
STATES = {'prepare': '准备', 'request': '点灯请求', 'confirmed': '点灯确认', 'ended': '结束'}


def clean(value, now):
  try:
    stamp = value['stamp']
    if (type(stamp) not in (int, float) or not math.isfinite(stamp) or not 0 <= now-stamp < MAX_AGE or
        value.get('version') != 1 or value['state'] not in STATES or value['origin'] not in ORIGINS or
        value['direction'] not in ('left', 'right') or value['reason'] not in REASONS or
        value['lamp'] not in ('left', 'right', 'both', 'off', 'unknown')):
      return None
    return {k: value[k] for k in ('version', 'stamp', 'state', 'origin', 'direction', 'reason', 'lamp')}
  except (KeyError, TypeError, ValueError):
    return None


class Reader:
  def __init__(self, path=PATH):
    self.path, self.next_read, self.value = path, 0., None

  def read(self, now=None):
    now = time.monotonic() if now is None else now
    if now >= self.next_read:
      self.next_read = now+.2
      try:
        with self.path.open('rb') as f:
          raw = f.read(MAX_BYTES+1)
        self.value = json.loads(raw) if len(raw) <= MAX_BYTES else None
      except (OSError, ValueError):
        self.value = None
    return clean(self.value, now)


_reader = Reader()


def current():
  return _reader.read()


def lines(value):
  direction = '左' if value['direction'] == 'left' else '右'
  lamp = {'left': '左灯 ON', 'right': '右灯 ON', 'both': '双灯 ON', 'off': 'OFF', 'unknown': '未确认'}[value['lamp']]
  return (f"{direction} · {ORIGINS[value['origin']]} · {STATES[value['state']]}",
          f"{REASONS[value['reason']]} / 车辆转向灯 {lamp}")


_widths = {}


def draw(x, y, width, font, size):
  value = current()
  if value is None:
    return
  import pyray as rl
  colors = {'prepare': (255, 200, 80), 'request': (120, 200, 255),
            'confirmed': (100, 240, 150), 'ended': (190, 190, 190)}
  color = rl.Color(*colors[value['state']], 255)
  rl.draw_rectangle(int(x), int(y), int(width), int(size*2.7), rl.Color(0, 0, 0, 180))
  for i, text in enumerate(lines(value)):
    # Keep the same bounded two-line badge on C3, C4 and the narrow USB panel.
    key = (id(font), text, size)
    if key not in _widths:
      if len(_widths) >= 128:
        _widths.clear()
      # Standalone Jetson HUD does not ship the system.ui runtime.
      _widths[key] = rl.measure_text_ex(font, text, size, 0).x  # noqa: TID251
    measured = _widths[key]
    fitted = min(size, size*(width-16)/max(measured, 1))
    rl.draw_text_ex(font, text, rl.Vector2(x+8, y+4+i*size*1.25), fitted, 0, color if i == 0 else rl.WHITE)
