#pragma once

#include <atomic>
#include <cstdint>
#include <mutex>
#include <string>
#include <vector>

#include <libusb-1.0/libusb.h>


#define TIMEOUT 0
#define SPI_BUF_SIZE 4096


// Transport-agnostic panda handle. zp's restructure went SPI-only, but the
// comma three's internal panda (HW type dos, STM32F4) is wired over USB -
// only the comma 3X (tres/cuatro) uses SPI. USB is restored 2026-10 so the
// restructured pandad keeps working on the comma three; Panda tries USB
// first and falls back to SPI.
class PandaCommsHandle {
public:
  PandaCommsHandle(std::string) {}
  virtual ~PandaCommsHandle() {}

  std::string hw_serial;
  std::atomic<bool> connected = true;
  std::atomic<bool> comms_healthy = true;

  virtual void cleanup() = 0;
  virtual int control_write(uint8_t request, uint16_t param1, uint16_t param2, unsigned int timeout=TIMEOUT) = 0;
  virtual int control_read(uint8_t request, uint16_t param1, uint16_t param2, unsigned char *data, uint16_t length, unsigned int timeout=TIMEOUT) = 0;
  virtual int bulk_write(unsigned char endpoint, unsigned char* data, int length, unsigned int timeout=TIMEOUT) = 0;
  virtual int bulk_read(unsigned char endpoint, unsigned char* data, int length, unsigned int timeout=TIMEOUT) = 0;
};

class PandaUsbHandle : public PandaCommsHandle {
public:
  PandaUsbHandle(std::string serial);
  ~PandaUsbHandle();

  int control_write(uint8_t request, uint16_t param1, uint16_t param2, unsigned int timeout=TIMEOUT);
  int control_read(uint8_t request, uint16_t param1, uint16_t param2, unsigned char *data, uint16_t length, unsigned int timeout=TIMEOUT);
  int bulk_write(unsigned char endpoint, unsigned char* data, int length, unsigned int timeout=TIMEOUT);
  int bulk_read(unsigned char endpoint, unsigned char* data, int length, unsigned int timeout=TIMEOUT);
  void cleanup();

  static std::vector<std::string> list();

private:
  libusb_context *ctx = NULL;
  libusb_device_handle *dev_handle = NULL;
  std::recursive_mutex hw_lock;
  void handle_usb_issue(int err, const char func[]);
};

class PandaSpiHandle : public PandaCommsHandle {
public:
  PandaSpiHandle(std::string serial);
  ~PandaSpiHandle();

  int control_write(uint8_t request, uint16_t param1, uint16_t param2, unsigned int timeout=TIMEOUT);
  int control_read(uint8_t request, uint16_t param1, uint16_t param2, unsigned char *data, uint16_t length, unsigned int timeout=TIMEOUT);
  int bulk_write(unsigned char endpoint, unsigned char* data, int length, unsigned int timeout=TIMEOUT);
  int bulk_read(unsigned char endpoint, unsigned char* data, int length, unsigned int timeout=TIMEOUT);
  void cleanup();

  static std::vector<std::string> list();

private:
  int spi_fd = -1;
  uint8_t tx_buf[SPI_BUF_SIZE];
  uint8_t rx_buf[SPI_BUF_SIZE];
  inline static std::recursive_mutex hw_lock;

  struct __attribute__((packed)) spi_header {
    uint8_t endpoint;
    uint32_t id;
    uint16_t tx_len;
    uint16_t rx_len;
  };
  struct __attribute__((packed)) spi_resp_header {
    uint8_t status;
    uint32_t id;
    uint16_t len;
  };

  int spi_transfer(uint8_t endpoint, uint32_t id, uint8_t *tx_data, uint16_t tx_len, uint8_t *rx_data, uint16_t max_rx_len, double deadline);
  int spi_transfer_retry(uint8_t endpoint, uint8_t *tx_data, uint16_t tx_len, uint8_t *rx_data, uint16_t max_rx_len, unsigned int timeout);
  int lltransfer(struct spi_ioc_transfer &t);

  spi_header header;
  uint32_t xfer_count = 0;
};
