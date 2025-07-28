#!/usr/bin/env python3
import json
import os
import re
import requests
import shutil
import sys
import time
import urllib.parse

from pathlib import Path

from openpilot.common.basedir import BASEDIR
from openpilot.frogpilot.assets.download_functions import GITLAB_URL, download_file, get_remote_file_size, get_repository_url, handle_error, handle_request_error, verify_download
from openpilot.frogpilot.common.frogpilot_utilities import delete_file, extract_tar, get_folder_size, run_cmd
from openpilot.frogpilot.common.frogpilot_variables import DEFAULT_CLASSIC_MODEL, DEFAULT_MODEL, DEFAULT_TINYGRAD_MODEL, MODELS_PATH, RESOURCES_REPO, TINYGRAD_FILES, GearShifter, \
                                                           params, params_default, params_memory, update_frogpilot_toggles

VERSION = "v16"

CANCEL_DOWNLOAD_PARAM = "CancelModelDownload"
DOWNLOAD_PROGRESS_PARAM = "ModelDownloadProgress"
MODEL_DOWNLOAD_PARAM = "ModelToDownload"
MODEL_DOWNLOAD_ALL_PARAM = "DownloadAllModels"
UPDATE_TINYGRAD_PARAM = "UpdateTinygrad"

TAR_FILE_NAME = f"Tinygrad_{VERSION}.tar.gz"

TINYGRAD_MODELD_PATH = Path(BASEDIR) / "frogpilot/tinygrad_modeld"
TINYGRAD_PATH = Path(BASEDIR) / "tinygrad"
TINYGRAD_REPO_PATH = Path(BASEDIR) / "tinygrad_repo"

class ModelManager:
  def __init__(self):
    self.downloading_model = False

    self.available_models = (params.get("AvailableModels", encoding="utf-8") or "").split(",")
    self.available_model_names = (params.get("AvailableModelNames", encoding="utf-8") or "").split(",")
    self.model_versions = (params.get("ModelVersions", encoding="utf-8") or "").split(",")

    self.model_sizes_path = MODELS_PATH / "model_sizes.json"
    self.tinygrad_size_path = MODELS_PATH / "tinygrad_size.json"

    self.session = requests.Session()
    self.session.headers.update({"User-Agent": "frogpilot-model-downloader/1.0 (https://github.com/FrogAi/FrogPilot)"})

  def check_models(self, boot_run, repo_url):
    downloaded_models = [path for path in MODELS_PATH.iterdir() if path.is_file()]

    for model_file in downloaded_models:
      if model_file.name not in {self.model_sizes_path.name, self.tinygrad_size_path.name} and not any(model in model_file.name for model in set(self.available_models)):
        print(f"Removing outdated model: {model_file}")
        delete_file(model_file)

    for onnx_file in MODELS_PATH.glob("*.onnx"):
      if onnx_file.is_file():
        print(f"Deleting .onnx file: {onnx_file}")
        delete_file(onnx_file)

    for tmp_file in MODELS_PATH.glob("tmp*"):
      if tmp_file.is_file():
        delete_file(tmp_file)

    if params.get("Model", encoding="utf-8") not in self.available_models:
      params.put("Model", params_default.get("Model", encoding="utf-8"))

    if not (not boot_run and params.get_bool("AutomaticallyDownloadModels")):
      return

    model_sizes = self.fetch_all_model_sizes(repo_url)
    if not model_sizes:
      print("No model size data available. Skipping model checks...")
      return

    local_model_sizes = self.load_model_sizes()

    needs_download = False
    for model, version in zip(self.available_models, self.model_versions):
      if version in {"v1", "v2", "v3", "v4", "v5", "v6"}:
        model_file = MODELS_PATH / f"{model}.thneed"
        if not model_file.is_file():
          needs_download = True
          continue

        expected_size = model_sizes.get(model_file.name)
        local_size = local_model_sizes.get(model_file.name)

        if expected_size > 0 and local_size != expected_size:
          print(f"Model {model} is outdated. Deleting {model_file}...")
          delete_file(model_file)
          needs_download = True
      else:
        for filename, _ in TINYGRAD_FILES:
          expected_file = MODELS_PATH / f"{model}_{filename}"
          if not expected_file.is_file():
            needs_download = True
            break

        if not needs_download:
          for suffix in ["driving_policy", "driving_vision"]:
            onnx_filename = f"{model}_{suffix}.onnx"

            expected_size = model_sizes.get(onnx_filename)
            local_size = local_model_sizes.get(onnx_filename)

            if expected_size > 0 and local_size != expected_size:
              needs_download = True
              break

        if needs_download:
          print(f"Model {model} is either missing required files or outdated. Deleting...")
          for filename, _ in TINYGRAD_FILES:
            delete_file(MODELS_PATH / f"{model}_{filename}")
          continue

    if needs_download:
      params_memory.put_bool(MODEL_DOWNLOAD_ALL_PARAM, True)

  def check_tinygrad(self, boot_run, repo_url):
    if not TINYGRAD_REPO_PATH.exists():
      print("Tinygrad directory not found, flagging for update...")
      params_memory.put_bool(UPDATE_TINYGRAD_PARAM, True)
    else:
      if boot_run:
        self.cleanup_tinygrad()

        current_size = get_folder_size(TINYGRAD_PATH) + get_folder_size(TINYGRAD_MODELD_PATH) + get_folder_size(TINYGRAD_REPO_PATH)
        previous_size = params.get_int("TinygradSize")

        if current_size != previous_size:
          print(f"Tinygrad version {VERSION} is outdated, previous_size: {previous_size}, current_size: {current_size}, flagging for update...")
          params_memory.put_bool(UPDATE_TINYGRAD_PARAM, True)
          params.put_int("TinygradSize", current_size)
          return

      tinygrad_url = f"{repo_url}/Tinygrad/{TAR_FILE_NAME}"

      expected_size = get_remote_file_size(tinygrad_url, self.session)
      local_size = next(iter(self.load_tinygrad_size().values()))

      if expected_size > 0 and local_size != expected_size:
        print(f"Tinygrad version {VERSION} is outdated, expected_size: {expected_size}, local_size: {local_size}, flagging for update...")
        params.put_bool("TinygradUpdateAvailable", True)
        params_memory.put_bool(UPDATE_TINYGRAD_PARAM, not boot_run and params.get_bool("AutomaticallyDownloadModels"))

  @staticmethod
  def cleanup_tinygrad():
    directories_to_clean = [TINYGRAD_MODELD_PATH, TINYGRAD_PATH, TINYGRAD_REPO_PATH]
    excluded_patterns = ["*.a", "*.cc", "*.h", "*.o", "*.onnx", "*.pkl", "*__pycache__*", "*tests*"]

    for directory in directories_to_clean:
      print(f"Cleaning up {directory}...")

      for pattern in excluded_patterns:
        for item in directory.rglob(pattern):
          print(f"Removing {item}...")
          delete_file(item)

    print("Tinygrad cleanup complete!")

  def compile_model(self, model_name, sm):
    params_memory.put(DOWNLOAD_PROGRESS_PARAM, "Compiling...")
    print(f"Compiling model '{model_name}'...")

    compile_script = TINYGRAD_REPO_PATH / "examples/openpilot/compile3.py"
    metadata_script = TINYGRAD_MODELD_PATH / "get_model_metadata.py"

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{env.get('PYTHONPATH')}:{TINYGRAD_REPO_PATH}"

    for suffix in ["driving_policy", "driving_vision"]:
      self.wait_for_offroad(sm)

      if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
        handle_error(None, "Download cancelled...", "Download cancelled...", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM)
        self.downloading_model = False
        return

      onnx_path = MODELS_PATH / f"{model_name}_{suffix}.onnx"
      output_path = MODELS_PATH / f"{model_name}_{suffix}_tinygrad.pkl"

      compile_command = [sys.executable, str(compile_script), str(onnx_path), str(output_path)]
      run_cmd(compile_command, success_message="Model compiled successfully!", fail_message="Failed to compile the model...", env=env)

      self.wait_for_offroad(sm)

      if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
        handle_error(None, "Download cancelled...", "Download cancelled...", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM)
        self.downloading_model = False
        return

      metadata_command = [sys.executable, str(metadata_script), str(onnx_path)]
      run_cmd(metadata_command, success_message=f"Successfully extracted metadata from {onnx_path.name}!", fail_message=f"Failed to extract metadata from {onnx_path.name}...")

      delete_file(onnx_path)

  def copy_default_model(self):
    classic_default_model_path = MODELS_PATH / f"{DEFAULT_CLASSIC_MODEL}.thneed"
    source_path = Path(__file__).parents[1] / "classic_modeld/models/supercombo.thneed"
    if source_path.is_file() and not classic_default_model_path.is_file():
      shutil.copyfile(source_path, classic_default_model_path)
      print(f"Copied the classic default model from {source_path} to {classic_default_model_path}")
      self.update_model_size(classic_default_model_path)

    default_model_path = MODELS_PATH / f"{DEFAULT_MODEL}.thneed"
    source_path = Path(__file__).parents[2] / "selfdrive/modeld/models/supercombo.thneed"
    if source_path.is_file() and not default_model_path.is_file():
      shutil.copyfile(source_path, default_model_path)
      print(f"Copied the default model from {source_path} to {default_model_path}")
      self.update_model_size(default_model_path)

    for filename, description in TINYGRAD_FILES:
      source = TINYGRAD_MODELD_PATH / "models" / filename
      target = MODELS_PATH / f"{DEFAULT_TINYGRAD_MODEL}_{filename}"
      if source.is_file() and not target.is_file():
        shutil.copyfile(source, target)
        print(f"Copied the tinygrad {description} from {source} to {target}")

  def download_all_models(self, sm):
    repo_url = get_repository_url(self.session)
    if not repo_url:
      handle_error(None, "GitHub and GitLab are offline...", "Repository unavailable", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM)
      return

    self.fetch_models(f"{repo_url}/Versions/model_names_{VERSION}.json", repo_url)

    for model in self.available_models:
      if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
        handle_error(None, "Download cancelled...", "Download cancelled...", MODEL_DOWNLOAD_ALL_PARAM, DOWNLOAD_PROGRESS_PARAM)
        return

      already_downloaded = [model_file for model_file in MODELS_PATH.iterdir() if model_file.is_file() and model in model_file.name]
      if already_downloaded:
        continue

      print(f"Model {model} is not downloaded. Preparing to download...")
      params_memory.put(DOWNLOAD_PROGRESS_PARAM, f"Downloading \"{self.available_model_names[self.available_models.index(model)]}\"...")

      self.download_model(model, sm)

    params_memory.put(DOWNLOAD_PROGRESS_PARAM, "All models downloaded!")

  def download_model(self, model_to_download, sm):
    self.downloading_model = True

    repo_url = get_repository_url(self.session)
    if not repo_url:
      handle_error(None, "GitHub and GitLab are offline...", "Repository unavailable", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM)
      self.downloading_model = False
      return

    if self.model_versions[self.available_models.index(model_to_download)] in {"v1", "v2", "v3", "v4", "v5", "v6"}:
      model_path = MODELS_PATH / f"{model_to_download}.thneed"
      model_url = f"{repo_url}/Models/{model_to_download}.thneed"

      print(f"Downloading model: {model_to_download}")
      download_file(CANCEL_DOWNLOAD_PARAM, model_path, DOWNLOAD_PROGRESS_PARAM, model_url, MODEL_DOWNLOAD_PARAM, self.session)

      if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
        handle_error(None, "Download cancelled...", "Download cancelled...", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM)
        self.downloading_model = False
        return

      if verify_download(model_path, model_url, self.session):
        print(f"Model {model_to_download} downloaded and verified successfully!")
        self.update_model_size(model_path)
        params_memory.put(DOWNLOAD_PROGRESS_PARAM, "Downloaded!")
        params_memory.remove(MODEL_DOWNLOAD_PARAM)
        self.downloading_model = False
        return

      print(f"Verification failed for model {model_to_download}. Retrying from GitLab...")
      fallback_url = f"{GITLAB_URL}/Models/{model_to_download}.thneed"
      download_file(CANCEL_DOWNLOAD_PARAM, model_path, DOWNLOAD_PROGRESS_PARAM, fallback_url, MODEL_DOWNLOAD_PARAM, self.session)

      if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
        handle_error(None, "Download cancelled...", "Download cancelled...", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM)
        self.downloading_model = False
        return

      if verify_download(model_path, fallback_url, self.session):
        print(f"Model {model_to_download} downloaded and verified successfully from GitLab!")
        self.update_model_size(model_path)
        params_memory.put(DOWNLOAD_PROGRESS_PARAM, "Downloaded!")
        params_memory.remove(MODEL_DOWNLOAD_PARAM)
        self.downloading_model = False
      else:
        handle_error(model_path, "Verification failed...", "GitLab verification failed", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM)
        self.downloading_model = False
    else:
      model_files = [
        ("driving_policy.onnx", "driving policy model"),
        ("driving_vision.onnx", "driving vision model"),
      ]

      for index, (file_name, description) in enumerate(model_files, start=1):
        filename = f"{model_to_download}_{file_name}"
        model_path = MODELS_PATH / filename
        model_url = f"{repo_url}/Models/{filename}"

        print(f"Downloading {description} for model: {model_to_download}")
        download_file(CANCEL_DOWNLOAD_PARAM, model_path, DOWNLOAD_PROGRESS_PARAM, model_url, MODEL_DOWNLOAD_PARAM, self.session, files=len(model_files), file_number=index)

        if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
          handle_error(None, "Download cancelled...", "Download cancelled...", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM)
          self.downloading_model = False
          return

        if verify_download(model_path, model_url, self.session):
          print(f"{description.capitalize()} for {model_to_download} downloaded and verified successfully!")
          continue

        print(f"Verification failed for {filename}. Retrying from GitLab...")
        fallback_url = f"{GITLAB_URL}/Models/{filename}"
        download_file(CANCEL_DOWNLOAD_PARAM, model_path, DOWNLOAD_PROGRESS_PARAM, fallback_url, MODEL_DOWNLOAD_PARAM, self.session)

        if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
          handle_error(None, "Download cancelled...", "Download cancelled...", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM)
          self.downloading_model = False
          return

        if verify_download(model_path, fallback_url, self.session):
          print(f"{description.capitalize()} for {model_to_download} downloaded and verified successfully from GitLab!")
        else:
          handle_error(model_path, "Verification failed...", f"GitLab verification failed for {filename}", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM)
          self.downloading_model = False
          return

      print(f"Updating model sizes for {model_to_download}...")
      for filename, _ in model_files:
        file_path = MODELS_PATH / f"{model_to_download}_{filename}"
        self.update_model_size(file_path)

      self.wait_for_offroad(sm)

      self.compile_model(model_to_download, sm)

      if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
        params_memory.put(DOWNLOAD_PROGRESS_PARAM, "Compilation cancelled...")
      else:
        params_memory.put(DOWNLOAD_PROGRESS_PARAM, "Downloaded!")
      params_memory.remove(MODEL_DOWNLOAD_PARAM)

      self.downloading_model = False

  def fetch_all_model_sizes(self, repo_url):
    if "github" in repo_url:
      api_url = f"https://api.github.com/repos/{RESOURCES_REPO}/contents?ref=Models"
    elif "gitlab" in repo_url:
      api_url = f"https://gitlab.com/api/v4/projects/{urllib.parse.quote_plus(RESOURCES_REPO)}/repository/tree?ref=Models"
    else:
      return {}

    try:
      response = self.session.get(api_url)
      response.raise_for_status()

      model_files = [file for file in response.json() if "." in file["name"]]

      if "gitlab" in repo_url:
        model_sizes = {}
        for file in model_files:
          metadata_url = f"https://gitlab.com/api/v4/projects/{urllib.parse.quote_plus(RESOURCES_REPO)}/repository/files/{urllib.parse.quote_plus(file['path'])}/raw?ref=Models"
          metadata_response = self.session.head(metadata_url)
          metadata_response.raise_for_status()
          model_sizes[file["name"]] = int(metadata_response.headers.get("content-length", 0))
        return model_sizes
      else:
        return {file["name"]: file["size"] for file in model_files if "size" in file}

    except Exception as error:
      handle_request_error(f"Failed to fetch model sizes from {'GitHub' if 'github' in repo_url else 'GitLab'}: {error}", None, None, None)
      return {}

  def fetch_models(self, url, repo_url, boot_run=False):
    try:
      response = self.session.get(url, timeout=10)
      response.raise_for_status()
      model_info = response.json().get("models", [])

      if model_info:
        self.update_model_params(model_info)
        self.check_models(boot_run, repo_url)
        self.check_tinygrad(boot_run, repo_url)
    except Exception as error:
      handle_request_error(error, None, None, None)
      return []

  def load_model_sizes(self):
    if self.model_sizes_path.is_file():
      with open(self.model_sizes_path) as f:
        return json.load(f)
    return {}

  def load_tinygrad_size(self):
    if self.tinygrad_size_path.is_file():
      with open(self.tinygrad_size_path) as f:
        return json.load(f)
    return {}

  def update_model_params(self, model_info):
    self.available_models = [model["id"] for model in model_info]
    self.available_model_names = [model["name"] for model in model_info]
    self.model_versions = [model["version"] for model in model_info]

    params.put("AvailableModels", ",".join(self.available_models))
    params.put("AvailableModelNames", ",".join(self.available_model_names))
    params.put("ModelVersions", ",".join(self.model_versions))
    print("Models list updated successfully!")

  def update_models(self, boot_run):
    if self.downloading_model:
      return

    repo_url = get_repository_url(self.session)
    if repo_url is None:
      print("GitHub and GitLab are offline...")
      return

    self.fetch_models(f"{repo_url}/Versions/model_names_{VERSION}.json", repo_url, boot_run)

  def update_model_size(self, file_path):
    sizes = self.load_model_sizes()
    sizes[file_path.name] = file_path.stat().st_size

    with open(self.model_sizes_path, "w") as f:
      json.dump(sizes, f, indent=2)
    print(f"Updated size for {file_path.name} in {self.model_sizes_path.name}")

  def update_tinygrad_size(self, file_path):
    sizes = {file_path.name: file_path.stat().st_size}
    with open(self.tinygrad_size_path, "w") as f:
      json.dump(sizes, f, indent=2)
    print(f"Updated size for {file_path.name} in {self.tinygrad_size_path.name}")

  def update_tinygrad(self):
    tinygrad_tar_path = Path("/data/tmp/tinygrad.tar.gz")

    repo_url = get_repository_url(self.session)
    if not repo_url:
      handle_error(None, "GitHub and GitLab are offline...", "Repository unavailable", None, None)
      return

    primary_url = f"{repo_url}/Tinygrad/{TAR_FILE_NAME}"
    fallback_url = f"https://gitlab.com/{RESOURCES_REPO}/-/raw/Tinygrad/{TAR_FILE_NAME}"

    try:
      print(f"Attempting to download tinygrad from {primary_url}...")
      download_file(CANCEL_DOWNLOAD_PARAM, tinygrad_tar_path, DOWNLOAD_PROGRESS_PARAM, primary_url, UPDATE_TINYGRAD_PARAM, self.session)

      if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
        handle_error(None, "Tinygrad update cancelled...", "Tinygrad update cancelled...", UPDATE_TINYGRAD_PARAM, DOWNLOAD_PROGRESS_PARAM)
        params_memory.remove("CancelModelDownload")
        return

      if not verify_download(tinygrad_tar_path, primary_url, self.session):
        print(f"Verification failed for {primary_url}. Retrying from GitLab...")
        download_file(CANCEL_DOWNLOAD_PARAM, tinygrad_tar_path, DOWNLOAD_PROGRESS_PARAM, fallback_url, UPDATE_TINYGRAD_PARAM, self.session)

      if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
        handle_error(None, "Tinygrad update cancelled...", "Tinygrad update cancelled...", UPDATE_TINYGRAD_PARAM, DOWNLOAD_PROGRESS_PARAM)
        params_memory.remove("CancelModelDownload")
        return

      if not verify_download(tinygrad_tar_path, fallback_url, self.session):
        handle_error(tinygrad_tar_path, "Verification Failed", "Tinygrad verification failed", UPDATE_TINYGRAD_PARAM, DOWNLOAD_PROGRESS_PARAM)
        return

      print("Tinygrad downloaded successfully! Proceeding with installation...")
      self.update_tinygrad_size(tinygrad_tar_path)

      print("Deleting old tinygrad directories...")
      delete_file(TINYGRAD_MODELD_PATH)
      print(f"Removed {TINYGRAD_MODELD_PATH}")
      delete_file(TINYGRAD_REPO_PATH)
      print(f"Removed {TINYGRAD_REPO_PATH}")
      delete_file(TINYGRAD_PATH)
      print(f"Removed old {TINYGRAD_PATH}")

      extract_tar(tinygrad_tar_path, Path(BASEDIR))

      print("Tinygrad update completed successfully!")

      params.put_bool("TinygradUpdateAvailable", False)
      params_memory.remove(UPDATE_TINYGRAD_PARAM)

      print("Updating old models...")

      installed_tinygrad_models = set()

      pkl_files = list(MODELS_PATH.glob("*.pkl"))
      for pkl_file in pkl_files:
        for model_name in self.available_models:
          if pkl_file.name.startswith(model_name):
            installed_tinygrad_models.add(model_name)
            break

      for pkl_file in pkl_files:
        delete_file(pkl_file)

      update_frogpilot_toggles()

      current_model = params.get("Model", encoding="utf-8")

      models_to_redownload = [current_model]
      models_to_redownload += [model for model in sorted(installed_tinygrad_models) if model != current_model]

      if models_to_redownload:
        print(f"Queueing the following models for redownload: {', '.join(models_to_redownload)}")
        self.fetch_models(f"{repo_url}/Versions/model_names_{VERSION}.json", repo_url)

        for model in models_to_redownload:
          while self.downloading_model:
            time.sleep(1)

          print(f"Adding the {model} model to the queue")

          if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
            handle_error(None, "Download cancelled...", "Download cancelled...", MODEL_DOWNLOAD_ALL_PARAM, DOWNLOAD_PROGRESS_PARAM)
            return

          already_downloaded = [model_file for model_file in MODELS_PATH.iterdir() if model_file.is_file() and model in model_file.name]
          if already_downloaded:
            continue

          params_memory.put(DOWNLOAD_PROGRESS_PARAM, f"Downloading \"{self.available_model_names[self.available_models.index(model)]}\"...")
          params_memory.put(MODEL_DOWNLOAD_PARAM, model)

          self.downloading_model = True
      else:
        print("No previously installed tinygrad models to redownload")

      update_frogpilot_toggles()

    except Exception as e:
      handle_error(tinygrad_tar_path, "Update Failed", f"An unexpected error occurred: {e}", UPDATE_TINYGRAD_PARAM, DOWNLOAD_PROGRESS_PARAM)

  def wait_for_offroad(self, sm):
    while sm["deviceState"].started and sm["carState"].gearShifter != GearShifter.park:
      sm.update()

      if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
        handle_error(None, "Download cancelled...", "Download cancelled...", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM)
        self.downloading_model = False
        return

      params_memory.put(DOWNLOAD_PROGRESS_PARAM, "Please go offroad...")

      time.sleep(1)
    return
