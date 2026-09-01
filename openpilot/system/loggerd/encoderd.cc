#include <algorithm>
#include <cassert>
#include <atomic>
#ifdef __COMMA_HARDWARE__
#include <exception>
#include <stdexcept>
#endif

#ifdef __COMMA_HARDWARE__
#include "system/loggerd/clip_encoder.h"
#endif
#include "system/loggerd/loggerd.h"
#include "system/loggerd/encoder/jpeg_encoder.h"

#ifdef __COMMA_HARDWARE__
#include "system/loggerd/encoder/v4l_encoder.h"
#define Encoder V4LEncoder
#else
#include "system/loggerd/encoder/ffmpeg_encoder.h"
#define Encoder FfmpegEncoder
#endif

ExitHandler do_exit;

struct EncoderdState {
  int max_waiting = 0;

  // Sync logic for startup
  std::atomic<int> encoders_ready = 0;
  std::atomic<uint32_t> start_frame_id = 0;
  bool camera_ready[VISION_STREAM_WIDE_ROAD + 1] = {};
  bool camera_synced[VISION_STREAM_WIDE_ROAD + 1] = {};
};

// Handle initial encoder syncing by waiting for all encoders to reach the same frame id
bool sync_encoders(EncoderdState *s, VisionStreamType cam_type, uint32_t frame_id) {
  if (s->camera_synced[cam_type]) return true;

  if (s->max_waiting > 1 && s->encoders_ready != s->max_waiting) {
    // add a small margin to the start frame id in case one of the encoders already dropped the next frame
    update_max_atomic(s->start_frame_id, frame_id + 2);
    if (std::exchange(s->camera_ready[cam_type], true) == false) {
      ++s->encoders_ready;
      LOGD("camera %d encoder ready", cam_type);
    }
    return false;
  } else {
    if (s->max_waiting == 1) update_max_atomic(s->start_frame_id, frame_id);
    bool synced = frame_id >= s->start_frame_id;
    s->camera_synced[cam_type] = synced;
    if (!synced) LOGD("camera %d waiting for frame %d, cur %d", cam_type, (int)s->start_frame_id, frame_id);
    return synced;
  }
}

void encoder_set_bitrate(std::unique_ptr<Encoder> &e) {
  static Params params;
  std::string val = params.get("LivestreamEncoderBitrate");
  if (val.empty()) return;
  int bitrate = std::stoi(val);
  e->set_bitrate(bitrate);
}

static bool livestream_camera_active(VisionStreamType stream_type) {
  // Encode all live cameras continuously so WebRTC can switch sources instantly.
  // The active-camera param is still used to request an IDR on the selected stream.
  return true;
}

static std::atomic<int> live_laggers{0};

static void encoder_set_live_lagging(bool is_live, bool lagging, bool active_cam) {
  if (!is_live || !active_cam) return;
  static Params params;
  if (lagging) {
    if (live_laggers.fetch_add(1, std::memory_order_relaxed) == 0) {
      params.putBool("LivestreamEncoderLagging", true);
    }
  } else {
    if (live_laggers.fetch_sub(1, std::memory_order_relaxed) == 1) {
      params.putBool("LivestreamEncoderLagging", false);
    }
  }
}

static bool cam_info_has_live_encoder(const LogCameraInfo &cam_info) {
  for (const auto &info : cam_info.encoder_infos) {
    if (info.is_live) return true;
  }
  return false;
}

void encoder_request_keyframe(std::unique_ptr<Encoder> &e) {
  static Params params;
  if (!params.getBool("LivestreamRequestKeyframe")) return;
  e->request_keyframe();
}

void encoder_thread(EncoderdState *s, const LogCameraInfo &cam_info) {
  util::set_thread_name(cam_info.thread_name);

  std::vector<std::unique_ptr<Encoder>> encoders;

  VisionIpcClient vipc_client = VisionIpcClient("camerad", cam_info.stream_type, false);

  std::unique_ptr<JpegEncoder> jpeg_encoder;

  int cur_seg = 0;
  while (!do_exit) {
    if (!vipc_client.connect(false)) {
      util::sleep_for(5);
      continue;
    }

    // init encoders
    if (encoders.empty()) {
      const VisionBuf &buf_info = vipc_client.buffers[0];
      LOGW("encoder %s init %zux%zu", cam_info.thread_name, buf_info.width, buf_info.height);
      assert(buf_info.width > 0 && buf_info.height > 0);

      for (const auto &encoder_info : cam_info.encoder_infos) {
        auto &e = encoders.emplace_back(new Encoder(encoder_info, buf_info.width, buf_info.height));
        e->encoder_open();
      }

      // Only one thumbnail can be generated per camera stream
      if (auto thumbnail_name = cam_info.encoder_infos[0].thumbnail_name) {
        jpeg_encoder = std::make_unique<JpegEncoder>(thumbnail_name, buf_info.width / 4, buf_info.height / 4);
      }
    }

    bool lagging = false;
    const bool has_live = cam_info_has_live_encoder(cam_info);
    while (!do_exit) {
      VisionIpcBufExtra extra;
      VisionBuf* buf = vipc_client.recv(&extra);
      if (buf == nullptr) continue;

      // detect loop around and drop the frames
      if (buf->get_frame_id() != extra.frame_id) {
        if (!lagging) {
          LOGE("encoder %s lag  buffer id: %" PRIu64 " extra id: %d", cam_info.thread_name, buf->get_frame_id(), extra.frame_id);
          lagging = true;
          encoder_set_live_lagging(has_live, true, livestream_camera_active(cam_info.stream_type));
        }
        continue;
      }
      if (lagging) {
        lagging = false;
        encoder_set_live_lagging(has_live, false, livestream_camera_active(cam_info.stream_type));
      }

      if (!sync_encoders(s, cam_info.stream_type, extra.frame_id)) {
        continue;
      }
      if (do_exit) break;

      // do rotation if required
      const int frames_per_seg = SEGMENT_LENGTH * MAIN_FPS;
      if (cur_seg >= 0 && extra.frame_id >= ((cur_seg + 1) * frames_per_seg) + s->start_frame_id) {
        for (auto &e : encoders) {
          e->encoder_close();
          e->encoder_open();
        }
        ++cur_seg;
      }

      // encode a frame
      for (int i = 0; i < encoders.size(); ++i) {
        if (cam_info.encoder_infos[i].is_live && !livestream_camera_active(cam_info.stream_type)) {
          continue;
        }
        if (cam_info.encoder_infos[i].is_live) {
          encoder_set_bitrate(encoders[i]);
          encoder_request_keyframe(encoders[i]);
        }

        int out_id = encoders[i]->encode_frame(buf, &extra);

        if (out_id == -1) {
          LOGE("Failed to encode frame. frame_id: %d", extra.frame_id);
        }
      }

      if (jpeg_encoder && (extra.frame_id % 1200 == 100)) {
        jpeg_encoder->pushThumbnail(buf, extra);
      }
    }
  }
}

template <size_t N>
void encoderd_thread(const LogCameraInfo (&cameras)[N]) {
  EncoderdState s;

  std::set<VisionStreamType> expected;
  for (const auto &cam : cameras) expected.insert(cam.stream_type);

  std::set<VisionStreamType> streams;
  while (!do_exit) {
    streams = VisionIpcClient::getAvailableStreams("camerad", false);
    if (std::includes(streams.begin(), streams.end(), expected.begin(), expected.end())) {
      break;
    }
    util::sleep_for(100);
  }

  if (!do_exit) {
    std::vector<std::thread> encoder_threads;
    for (auto stream : streams) {
      auto it = std::find_if(std::begin(cameras), std::end(cameras),
                             [stream](auto &cam) { return cam.stream_type == stream; });
      assert(it != std::end(cameras));
      ++s.max_waiting;
      encoder_threads.push_back(std::thread(encoder_thread, &s, *it));
    }

    for (auto &t : encoder_threads) t.join();
  }
}

int main(int argc, char* argv[]) {
#ifdef __COMMA_HARDWARE__
  if (argc > 1 && std::string(argv[1]) == "--clip") {
    if (argc < 6) {
      fprintf(stderr, "usage: encoderd --clip OUTPUT START DURATION [--bitrate BPS] [--speedup N] "
                      "[--metadata JSON] SEGMENT [SEGMENT ...]\n");
      return 2;
    }
    try {
      int bitrate = 5'000'000;
      int speedup = 1;
      std::string metadata;
      int input_arg = 5;
      while (input_arg < argc && std::string(argv[input_arg]).rfind("--", 0) == 0) {
        const std::string option = argv[input_arg++];
        if (option == "--") break;
        if (input_arg == argc) throw std::invalid_argument("missing clip option value");
        if (option == "--bitrate") bitrate = std::stoi(argv[input_arg++]);
        else if (option == "--speedup") speedup = std::stoi(argv[input_arg++]);
        else if (option == "--metadata") metadata = argv[input_arg++];
        else throw std::invalid_argument("unknown clip option: " + option);
      }
      if (input_arg == argc) throw std::invalid_argument("missing clip input");
      std::vector<std::string> inputs(argv + input_arg, argv + argc);
      return encode_clip(inputs, argv[2], std::stod(argv[3]), std::stod(argv[4]),
                         bitrate, speedup, metadata);
    } catch (const std::exception &e) {
      fprintf(stderr, "clip encoding failed: %s\n", e.what());
      return 1;
    }
  }
#endif
  if (!Hardware::PC()) {
    int ret;
    ret = util::set_realtime_priority(52);
    assert(ret == 0);
    ret = util::set_core_affinity({3});
    assert(ret == 0);
  }
  if (argc > 1) {
    std::string arg1(argv[1]);
    if (arg1 == "--stream") {
      encoderd_thread(stream_cameras_logged);
    } else {
      LOGE("Argument '%s' is not supported", arg1.c_str());
    }
  } else {
    encoderd_thread(cameras_logged);
  }
  return 0;
}
