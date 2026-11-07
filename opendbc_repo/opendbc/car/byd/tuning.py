#!/usr/bin/env python3

class Tuning:
  # 仅开启非线性模式，但又没有选NNFF时候才有效
  LAT_SIGLIN_TABLE = [4.867, 1.09, 0.243]

  # 方向盘手动偏差
  STEERING_ANGLE_OFFSET = 0

  # modified stock long control 原车long控制的速度平滑百分比设定
  K_ACCEL_BP = [40, 50, 60, 70, 80]  # meters BP是离前车距离

  K_ACCEL_POS_4BAR = [0.8, 0.7, 0.7, 0.7, 0.7]  # acceleration 加速的百分比
  K_ACCEL_NEG_4BAR = [1.0, 0.8, 0.7, 0.7, 0.7]  # deceleration 减速的百分比

  K_ACCEL_POS_3BAR = [0.8, 0.7, 0.7, 0.7, 0.7]
  K_ACCEL_NEG_3BAR = [1.0, 0.9, 0.8, 0.7, 0.7]

  K_ACCEL_POS_2BAR = [0.8, 0.8, 0.7, 0.7, 0.7]
  K_ACCEL_NEG_2BAR = [1.0, 1.0, 0.9, 0.8, 0.7]

  K_ACCEL_POS_1BAR = [1.0, 1.0, 1.0, 0.9, 0.8]
  K_ACCEL_NEG_1BAR = [1.1, 1.0, 1.0, 1.0, 0.9]

  # 人为扭动方向盘的阈值，大于这个值才认为方向盘被故意扭动了，变道辅助涉及它
  STEER_PRESSED_THRESHOLD = 56

  # N3 (SA6): EPS_DrvrSteerTq is physical Nm (x0.02); driver-override threshold in Nm
  N3_STEER_PRESSED_NM = 0.7

  # 解决某些D9或者唐车型，离手时间过久，EPS会退出问题
  HANDSOFF_ANGLE = [4, 11, 18]
  HANDSOFF_PERIOD = [5, 10, 15]

  # 禁用EPS故障检查
  DISABLE_EPS_WARNING = False
  DISABLE_EPS_TEMPORARY_FAULT = False
  DISABLE_EPS_PERMANENT_FAULT = False

  EPS_ANGLE_EXCEED_WARNING_CNT = 3
  EPS_ANGLE_SPEED_WARNING_CNT = 3
  EPS_STATE_WARNING_CNT = 20
