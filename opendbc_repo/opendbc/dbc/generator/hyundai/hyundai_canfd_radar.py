#!/usr/bin/env python3
"""Generate the CAN-FD radar track DBCs.

Three address families, each with its own object layout:

  0x210 + 16  group 1, two objects per message (the *_1 and *_2 signal families)
  0x3a5 + 32  group 2, one object per message
  0x400 + 30  group 3, a 30-slot object list with an empty-distance sentinel

Which group a car broadcasts is detected at fingerprint time (HyundaiExtFlags) and the
radar interface decodes accordingly, so all three must be present.

Ported from cp. The DBC body is written against this repo's generator contract: expose
generate() returning {filename: content} rather than writing a file, which is what
opendbc/dbc/generator/generator.py imports and calls.
"""


def generate() -> dict[str, str]:
  parts = ["""
VERSION ""


NS_ :
    NS_DESC_
    CM_
    BA_DEF_
    BA_
    VAL_
    CAT_DEF_
    CAT_
    FILTER
    BA_DEF_DEF_
    EV_DATA_
    ENVVAR_DATA_
    SGTYPE_
    SGTYPE_VAL_
    BA_DEF_SGTYPE_
    BA_SGTYPE_
    SIG_TYPE_REF_
    VAL_TABLE_
    SIG_GROUP_
    SIG_VALTYPE_
    SIGTYPE_VALTYPE_
    BO_TX_BU_
    BA_DEF_REL_
    BA_REL_
    BA_DEF_DEF_REL_
    BU_SG_REL_
    BU_EV_REL_
    BU_BO_REL_
    SG_MUL_VAL_

BS_:

BU_: XXX
    """]

  # Group 1: 16 messages, two objects each.
  for a in range(0x210, 0x210 + 16):
    parts.append(f"""

BO_ {a} RADAR_TRACK_{a:x}: 32 RADAR
 SG_ NEW_SIGNAL_25 : 26|3@0+ (1,0) [0|7] "" XXX
 SG_ NEW_SIGNAL_24 : 28|2@0+ (1,0) [0|3] "" XXX
 SG_ NEW_SIGNAL_21 : 36|5@0+ (1,0) [0|31] "" XXX
 SG_ NEW_SIGNAL_20 : 39|3@0+ (1,0) [0|7] "" XXX
 SG_ VALID_CNT1 : 47|8@0+ (1,0) [0|255] "" XXX
 SG_ NEW_SIGNAL_15 : 51|4@0+ (1,0) [0|15] "" XXX
 SG_ NEW_SIGNAL_14 : 55|4@0+ (1,0) [0|15] "" XXX
 SG_ NEW_SIGNAL_5 : 63|8@0- (1,0) [0|255] "" XXX
 SG_ LONG_DIST1 : 64|12@1+ (0.05,0) [0|4095] "" XXX
 SG_ LAT_DIST1 : 76|12@1- (0.05,0) [0|4095] "" XXX
 SG_ REL_SPEED1 : 88|14@1- (0.01,0) [0|16383] "" XXX
 SG_ NEW_SIGNAL_16 : 103|2@0+ (1,0) [0|3] "" XXX
 SG_ LAT_SPEED1 : 104|13@1- (0.01,0) [0|8191] "" XXX
 SG_ REL_ACCEL1 : 118|10@1- (0.05,0) [0|1023] "" XXX
 SG_ NEW_SIGNAL_27 : 154|3@0+ (1,0) [0|7] "" XXX
 SG_ NEW_SIGNAL_26 : 156|2@0+ (1,0) [0|3] "" XXX
 SG_ NEW_SIGNAL_23 : 164|5@0+ (1,0) [0|31] "" XXX
 SG_ NEW_SIGNAL_22 : 167|3@0+ (1,0) [0|7] "" XXX
 SG_ VALID_CNT2 : 175|8@0+ (1,0) [0|255] "" XXX
 SG_ NEW_SIGNAL_13 : 179|4@0+ (1,0) [0|15] "" XXX
 SG_ NEW_SIGNAL_12 : 183|4@0+ (1,0) [0|15] "" XXX
 SG_ NEW_SIGNAL_11 : 191|8@0- (1,0) [0|255] "" XXX
 SG_ LONG_DIST2 : 192|12@1+ (0.05,0) [0|4095] "" XXX
 SG_ LAT_DIST2 : 204|12@1- (0.05,0) [0|4095] "" XXX
 SG_ REL_SPEED2 : 216|14@1- (0.01,0) [0|16383] "" XXX
 SG_ NEW_SIGNAL_17 : 231|2@0+ (1,0) [0|3] "" XXX
 SG_ LAT_SPEED2 : 232|13@1- (0.01,0) [0|8191] "" XXX
 SG_ REL_ACCEL2 : 246|10@1- (0.05,0) [0|1023] "" XXX
    """)

  # Group 2: 32 messages, one object each.
  for a in range(0x3a5, 0x3a5 + 32):
    parts.append(f"""

BO_ {a} RADAR_TRACK_{a:x}: 24 RADAR
 SG_ VALID : 25|2@0+ (1,0) [0|3] "" XXX
 SG_ VALID2 : 28|2@0+ (1,0) [0|3] "" XXX
 SG_ PROB : 30|10@1+ (1,0) [0|1023] "" XXX
 SG_ VALID_CNT : 47|8@0+ (1,0) [0|255] "" XXX
 SG_ NEW_SIGNAL_7 : 51|4@0+ (1,0) [0|15] "" XXX
 SG_ NEW_SIGNAL_6 : 55|4@0+ (1,0) [0|15] "" XXX
 SG_ NEW_SIGNAL_2 : 62|7@0- (1,0) [0|127] "" XXX
 SG_ LONG_DIST : 63|13@1+ (0.05,0) [0|8191] "" XXX
 SG_ LAT_DIST : 76|12@1- (0.05,0) [0|4095] "" XXX
 SG_ REL_SPEED : 88|14@1- (0.01,0) [0|16383] "" XXX
 SG_ IN_MYLANE : 103|2@0+ (1,0) [0|3] "" XXX
 SG_ LAT_SPEED : 104|13@1- (0.01,0) [0|8191] "" XXX
 SG_ REL_ACCEL : 118|10@1- (0.05,0) [0|1023] "" XXX 
    """)

  # Group 3: 30 one-object messages, empty distance sentinel 0x7ff.
  for a in range(0x400, 0x400 + 30):
    parts.append(f"""

BO_ {a} RADAR_TRACK_{a:x}: 24 RADAR
 SG_ OBJECT_ID : 24|7@1+ (1,0) [0|127] "" XXX
 SG_ OBJECT_LENGTH : 41|7@1+ (0.1,0) [0|12.7] "m" XXX
 SG_ LONG_DIST : 64|11@1+ (0.1,0) [0|204.7] "m" XXX
 SG_ LAT_DIST : 75|12@1- (0.05,0) [-102.4|102.35] "m" XXX
 SG_ REL_SPEED : 87|11@1- (0.1,0) [-102.4|102.3] "m/s" XXX
    """)

  return {"hyundai_canfd_radar.dbc": "".join(parts)}
