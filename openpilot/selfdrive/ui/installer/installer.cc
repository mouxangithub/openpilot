#include <array>
#include <cassert>
#include <cstddef>
#include <fstream>
#include <map>
#include <string>

#include "common/swaglog.h"
#include "common/util.h"
#include "common/hardware/hw.h"
#include "raylib.h"

int freshClone();
int cachedFetch(const std::string &cache);
int executeGitCommand(const std::string &cmd);

// Fork installer generator (openpilot-installer-generator) patches these fixed slots in the ELF.
#ifdef INSTALLER_USE_PLACEHOLDERS
#define GIT_URL "https://github.com/27182818284590452353602874713526624977572470936999595"
#define BRANCH_SLOT "161803398874989484820458683436563811772030917980576286213544862270526046281890244970720720418939113748475408807538689175212663386222353693179318006076672635443338908659593958290563832266131992829026788067520876689250171169620703222104321626954862629631361"
#define LOADING_MSG_SLOT "314159265358979323846264338327950288419"
#else
std::string get_str(std::string const s) {
  std::string::size_type pos = s.find('?');
  assert(pos != std::string::npos);
  return s.substr(0, pos);
}

const std::string GIT_URL_BUILTIN = get_str("https://github.com/commaai/openpilot.git" "?                                                                ");
const std::string BRANCH_BUILTIN = get_str(BRANCH "?                                                                ");
#endif

#define GIT_SSH_URL "git@github.com:commaai/openpilot.git"
#define CONTINUE_PATH "/data/continue.sh"

const std::string INSTALL_PATH = "/data/openpilot";
const std::string VALID_CACHE_PATH = "/data/.openpilot_cache";

#define TMP_INSTALL_PATH "/data/tmppilot"

const int FONT_SIZE = 160;

extern const uint8_t str_continue[] asm("_binary_selfdrive_ui_installer_continue_openpilot_sh_start");
extern const uint8_t str_continue_end[] asm("_binary_selfdrive_ui_installer_continue_openpilot_sh_end");
extern const uint8_t inter_ttf[] asm("_binary_selfdrive_ui_installer_inter_ascii_ttf_start");
extern const uint8_t inter_ttf_end[] asm("_binary_selfdrive_ui_installer_inter_ascii_ttf_end");
extern const uint8_t inter_light_ttf[] asm("_binary_selfdrive_assets_fonts_Inter_Light_ttf_start");
extern const uint8_t inter_light_ttf_end[] asm("_binary_selfdrive_assets_fonts_Inter_Light_ttf_end");
extern const uint8_t inter_bold_ttf[] asm("_binary_selfdrive_assets_fonts_Inter_Bold_ttf_start");
extern const uint8_t inter_bold_ttf_end[] asm("_binary_selfdrive_assets_fonts_Inter_Bold_ttf_end");

Font font_inter;
Font font_roman;
Font font_display;

const bool tici_device = Hardware::get_device_type() == cereal::InitData::DeviceType::TICI ||
                         Hardware::get_device_type() == cereal::InitData::DeviceType::TIZI;

std::string trim_slot(const char *slot) {
  std::string s(slot);
  const auto nul = s.find('\0');
  if (nul != std::string::npos) {
    s.resize(nul);
  }
  while (!s.empty() && (s.back() == ' ' || s.back() == '\0')) {
    s.pop_back();
  }
  return s;
}

std::string git_url() {
#ifdef INSTALLER_USE_PLACEHOLDERS
  return trim_slot(GIT_URL);
#else
  return GIT_URL_BUILTIN;
#endif
}

std::string branch_name() {
#ifdef INSTALLER_USE_PLACEHOLDERS
  return trim_slot(BRANCH_SLOT);
#else
  return BRANCH_BUILTIN;
#endif
}

std::string loading_msg() {
#ifdef INSTALLER_USE_PLACEHOLDERS
  return trim_slot(LOADING_MSG_SLOT);
#else
  return "openpilot";
#endif
}

void run(const char* cmd) {
  int err = std::system(cmd);
  assert(err == 0);
}

void finishInstall() {
  BeginDrawing();
    ClearBackground(BLACK);
    if (tici_device) {
      const char *m = "Finishing install...";
      int text_width = MeasureText(m, FONT_SIZE);
      DrawTextEx(font_display, m, (Vector2){(float)(GetScreenWidth() - text_width)/2 + FONT_SIZE, (float)(GetScreenHeight() - FONT_SIZE)/2}, FONT_SIZE, 0, WHITE);
    } else {
      DrawTextEx(font_display, "finishing setup", (Vector2){12, 0}, 77, 0, (Color){255, 255, 255, (unsigned char)(255 * 0.9)});
    }
  EndDrawing();
  util::sleep_for(60 * 1000);
}

void renderProgress(int progress) {
  const std::string title = "Installing " + loading_msg();

  BeginDrawing();
    ClearBackground(BLACK);
    if (tici_device) {
      DrawTextEx(font_inter, title.c_str(), (Vector2){150, 290}, 110, 0, WHITE);
      Rectangle bar = {150, 570, (float)GetScreenWidth() - 300, 72};
      DrawRectangleRec(bar, (Color){41, 41, 41, 255});
      progress = std::clamp(progress, 0, 100);
      bar.width *= progress / 100.0f;
      DrawRectangleRec(bar, (Color){70, 91, 234, 255});
      DrawTextEx(font_inter, (std::to_string(progress) + "%").c_str(), (Vector2){150, 670}, 85, 0, WHITE);
    } else {
      DrawTextEx(font_display, "installing...", (Vector2){12, 0}, 77, 0, (Color){255, 255, 255, (unsigned char)(255 * 0.9)});
      const std::string percent_str = std::to_string(progress) + "%";
      DrawTextEx(font_inter, percent_str.c_str(), (Vector2){12, (float)(GetScreenHeight() - 154 + 20)}, 154, 0,
                 (Color){255, 255, 255, (unsigned char)(255 * 0.9 * 0.65)});
    }

  EndDrawing();
}

int doInstall() {
  while (!util::system_time_valid()) {
    util::sleep_for(500);
    LOGD("Waiting for valid time");
  }

  run("rm -rf " TMP_INSTALL_PATH);

  if (util::file_exists(INSTALL_PATH) && util::file_exists(VALID_CACHE_PATH)) {
    return cachedFetch(INSTALL_PATH);
  } else {
    return freshClone();
  }
}

int freshClone() {
  LOGD("Doing fresh clone");
  const auto url = git_url();
  const auto branch = branch_name();
  std::string cmd;
  if (branch.empty()) {
    cmd = util::string_format("git clone --progress %s --depth=1 --recurse-submodules %s 2>&1",
                              url.c_str(), TMP_INSTALL_PATH);
  } else {
    cmd = util::string_format("git clone --progress %s -b %s --depth=1 --recurse-submodules %s 2>&1",
                              url.c_str(), branch.c_str(), TMP_INSTALL_PATH);
  }
  return executeGitCommand(cmd);
}

int cachedFetch(const std::string &cache) {
  LOGD("Fetching with cache: %s", cache.c_str());

  const auto url = git_url();
  const auto branch = branch_name();

  run(util::string_format("cp -rp %s %s", cache.c_str(), TMP_INSTALL_PATH).c_str());
  run(util::string_format("cd %s && git remote set-url origin %s", TMP_INSTALL_PATH, url.c_str()).c_str());
  if (!branch.empty()) {
    run(util::string_format("cd %s && git remote set-branches --add origin %s", TMP_INSTALL_PATH, branch.c_str()).c_str());
  }

  renderProgress(10);

  if (branch.empty()) {
    return executeGitCommand(util::string_format("cd %s && git fetch --progress origin 2>&1", TMP_INSTALL_PATH));
  }
  return executeGitCommand(util::string_format("cd %s && git fetch --progress origin %s 2>&1", TMP_INSTALL_PATH, branch.c_str()));
}

int executeGitCommand(const std::string &cmd) {
  static const std::array stages = {
    std::pair{"Receiving objects: ", 91},
    std::pair{"Resolving deltas: ", 2},
    std::pair{"Updating files: ", 7},
  };

  FILE *pipe = popen(cmd.c_str(), "r");
  if (!pipe) return -1;

  char buffer[512];
  while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
    std::string line(buffer);
    int base = 0;
    for (const auto &[text, weight] : stages) {
      if (line.find(text) != std::string::npos) {
        size_t percentPos = line.find("%");
        if (percentPos != std::string::npos && percentPos >= 3) {
          int percent = std::stoi(line.substr(percentPos - 3, 3));
          int progress = base + int(percent / 100. * weight);
          renderProgress(progress);
        }
        break;
      }
      base += weight;
    }
  }
  return pclose(pipe);
}

void cloneFinished(int exitCode) {
  LOGD("git finished with %d", exitCode);
  assert(exitCode == 0);

  const auto branch = branch_name();

  renderProgress(100);

  int err = chdir(TMP_INSTALL_PATH);
  assert(err == 0);
  if (!branch.empty()) {
    run(("git checkout " + branch).c_str());
    run(("git reset --hard origin/" + branch).c_str());
  }
  run("git submodule update --init");

  run(("rm -f " + VALID_CACHE_PATH).c_str());
  run(("rm -rf " + INSTALL_PATH).c_str());
  run(util::string_format("mv %s %s", TMP_INSTALL_PATH, INSTALL_PATH.c_str()).c_str());

#ifdef INTERNAL
  run("mkdir -p /data/params/d/");

  const std::string ssh_keys = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMX2kU8eBZyEWmbq0tjMPxksWWVuIV/5l64GabcYbdpI";
  std::map<std::string, std::string> params = {
    {"SshEnabled", "1"},
    {"RecordFrontLock", "1"},
    {"GithubSshKeys", ssh_keys},
  };
  for (const auto& [key, value] : params) {
    std::ofstream param;
    param.open("/data/params/d/" + key);
    param << value;
    param.close();
  }
  run(("cd " + INSTALL_PATH + " && "
      "git remote set-url origin --push " GIT_SSH_URL " && "
      "git config --replace-all remote.origin.fetch \"+refs/heads/*:refs/remotes/origin/*\"").c_str());
#endif

  FILE *of = fopen("/data/continue.sh.new", "wb");
  assert(of != NULL);

  size_t num = str_continue_end - str_continue;
  size_t num_written = fwrite(str_continue, 1, num, of);
  assert(num == num_written);
  fclose(of);

  run("chmod +x /data/continue.sh.new");
  run("mv /data/continue.sh.new " CONTINUE_PATH);

  finishInstall();
}

int main(int argc, char *argv[]) {
  if (tici_device) {
    InitWindow(2160, 1080, "Installer");
  } else {
    InitWindow(536, 240, "Installer");
  }

  font_inter = LoadFontFromMemory(".ttf", inter_ttf, inter_ttf_end - inter_ttf, FONT_SIZE, NULL, 0);
  font_roman = LoadFontFromMemory(".ttf", inter_light_ttf, inter_light_ttf_end - inter_light_ttf, FONT_SIZE, NULL, 0);
  font_display = LoadFontFromMemory(".ttf", inter_bold_ttf, inter_bold_ttf_end - inter_bold_ttf, FONT_SIZE, NULL, 0);
  SetTextureFilter(font_inter.texture, TEXTURE_FILTER_BILINEAR);
  SetTextureFilter(font_roman.texture, TEXTURE_FILTER_BILINEAR);
  SetTextureFilter(font_display.texture, TEXTURE_FILTER_BILINEAR);

  if (util::file_exists(CONTINUE_PATH)) {
    finishInstall();
  } else {
    renderProgress(0);
    int result = doInstall();
    cloneFinished(result);
  }

  CloseWindow();
  UnloadFont(font_inter);
  UnloadFont(font_roman);
  UnloadFont(font_display);
  return 0;
}
