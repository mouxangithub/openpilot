#pragma once

// The STM32F413 has no digital temperature sensor (DTS) peripheral. Its analog
// temperature sensor sits on ADC1_IN18, which is taken over by VBAT while
// ADC_CCR_VBATE is set (see lladc.h), so there is nothing to read here.
// 0.0f is the same "no measurement" value the H7 driver returns.

void dts_init(void) {
}

float dts_get_temperature(void) {
  return 0.0f;
}
