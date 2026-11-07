#pragma once

// ///////////////////////////////////////////////////////////// //
// Hardware abstraction layer for all different supported boards //
// ///////////////////////////////////////////////////////////// //
#include "board/boards/board_declarations.h"
#include "board/boards/unused_funcs.h"

// ///// Board definition and detection ///// //
#include "board/stm32h7/lladc.h"
#include "board/stm32h7/lldts.h"
#include "board/drivers/harness.h"
#include "board/drivers/fan.h"
#include "board/stm32h7/llfan.h"
#include "board/stm32h7/sound.h"
#include "board/drivers/fake_siren.h"
#include "board/drivers/clock_source.h"
#include "board/boards/red.h"
#include "board/boards/tres.h"
#include "board/boards/cuatro.h"


void detect_board_type(void) {
  // On STM32H7 pandas, we use two different sets of pins.
  const uint8_t id1 = detect_with_pull(GPIOF, 7, PULL_UP) |
                     (detect_with_pull(GPIOF, 8, PULL_UP) << 1U) |
                     (detect_with_pull(GPIOF, 9, PULL_UP) << 2U) |
                     (detect_with_pull(GPIOF, 10, PULL_UP) << 3U);

  const uint8_t id2 = detect_with_pull(GPIOD, 4, PULL_UP) |
                     (detect_with_pull(GPIOD, 5, PULL_UP) << 1U) |
                     (detect_with_pull(GPIOD, 6, PULL_UP) << 2U) |
                     (detect_with_pull(GPIOD, 7, PULL_UP) << 3U);

  if (id2 == 3U) {
    hw_type = HW_TYPE_CUATRO;
    current_board = &board_cuatro;
  } else if (id1 == 0U) {
    hw_type = HW_TYPE_RED_PANDA;
    current_board = &board_red;
  } else if (id1 == 1U) {
    // deprecated RED_PANDA_V2 straps; on clone hardware (domestic C3XL
    // built-in pandas) these pins float to this combination. Default to
    // tres instead of UNKNOWN - see the fallback comment below
    hw_type = HW_TYPE_TRES;
    current_board = &board_tres;
  } else if (id1 == 2U) {
    hw_type = HW_TYPE_TRES;
    current_board = &board_tres;
  } else {
    // Domestic C3XL built-in pandas have non-standard ID pin straps that
    // match no known combination. Leaving hw_type at UNKNOWN makes main()
    // assert_fatal() BEFORE usb_init(), so the app never enumerates at all
    // (flash + jump succeed, board goes USB-silent). Default to tres - the
    // comma 3X internal panda this hardware clones - so the app boots and
    // enumerates (same approach as the F4 dos fallback).
    hw_type = HW_TYPE_TRES;
    current_board = &board_tres;
    print("Hardware type is UNKNOWN, defaulting to TRES!\n");
  }
}
