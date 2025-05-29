# tsk/reboot_menu/actions.py
import os
import shutil
import sys  # Import the sys module

from tsk.common.env import is_agnos, RECOMMENDED_OP_USER, RECOMMENDED_OP_BRANCH, RECOMMENDED_OP_DIR, ALTERNATE_OP_USER, \
  ALTERNATE_OP_BRANCH, ALTERNATE_OP_DIR
from tsk.common.key_file_manager import KeyFileManager
from tsk.ui.dialog import YesNoDialog


class Rebooter:
  # Actions based on launch_chffrplus.sh
  # Reboot is handled in that sh

  CONTINUE_FILE = "/data/continue.sh"
  OPENPILOT_DIR = "/data/openpilot"

  def __init__(self):
    self.is_agnos: bool = is_agnos()

  def recommended_action(self):
    print("Recommended button pressed")
    key = KeyFileManager().installed_key
    if key:
      question = f"Key installed: {key}\n\n"
    else:
      question = "!!!! Key not installed.\n" \
                 "!!!! Comma can't drive your car.\n\n"
    question += f"Reboot and install {RECOMMENDED_OP_USER}/{RECOMMENDED_OP_BRANCH}?"
    should_reboot = YesNoDialog.ask(question)
    if not should_reboot:
      print("Action cancelled")
      return
    print("Action confirmed")

    # Remove /data/openpilot
    if self.is_agnos:
      shutil.rmtree(self.OPENPILOT_DIR, ignore_errors=True)
    print(f"Removed {self.OPENPILOT_DIR}")

    # Remove /data/tsk-alternate
    if self.is_agnos:
      shutil.rmtree(ALTERNATE_OP_DIR, ignore_errors=True)
    print(f"Removed {ALTERNATE_OP_DIR}")

    # Move /data/tsk-recommended to /data/openpilot
    if self.is_agnos:
      shutil.move(RECOMMENDED_OP_DIR, self.OPENPILOT_DIR)
    print(f"Moved {RECOMMENDED_OP_DIR} to {self.OPENPILOT_DIR}")

    sys.exit(0)

  def alternate_action(self):
    print("Alternate button pressed")
    key = KeyFileManager().installed_key
    if key:
      question = f"Key installed: {key}\n\n"
    else:
      question = "!!!! Key not installed.\n" \
                 "!!!! Comma can't drive your car.\n\n"
    question += f"Reboot and install {ALTERNATE_OP_USER}/{ALTERNATE_OP_BRANCH}?"
    should_reboot = YesNoDialog.ask(question)
    if not should_reboot:
      print("Action cancelled")
      return
    print("Action confirmed")

    # Remove /data/openpilot
    if self.is_agnos:
      shutil.rmtree(self.OPENPILOT_DIR, ignore_errors=True)
    print(f"Removed {self.OPENPILOT_DIR}")

    # Remove /data/tsk-recommended
    if self.is_agnos:
      shutil.rmtree(RECOMMENDED_OP_DIR, ignore_errors=True)
    print(f"Removed {RECOMMENDED_OP_DIR}")

    # Move /data/tsk-alternate to /data/openpilot
    if self.is_agnos:
      shutil.move(ALTERNATE_OP_DIR, self.OPENPILOT_DIR)
    print(f"Moved {ALTERNATE_OP_DIR} to {self.OPENPILOT_DIR}")

    sys.exit(0)

  def bail_action(self):
    print("Bail button pressed")
    key = KeyFileManager().installed_key
    if key:
      question = f"Key installed: {key}\n\n"
    else:
      question = "!!!! Key not installed.\n" \
                 "!!!! Comma can't drive your car.\n\n"
    question += "Reboot and install a different fork/branch?"
    should_reboot = YesNoDialog.ask(question)
    if not should_reboot:
      print("Action cancelled")
      return
    print("Action confirmed")

    # Remove /data/tsk-recommended since it won't be used
    if self.is_agnos:
      shutil.rmtree(RECOMMENDED_OP_DIR, ignore_errors=True)
    print(f"Removed {RECOMMENDED_OP_DIR}")

    # Remove /data/tsk-alternate since it won't be used
    if self.is_agnos:
      shutil.rmtree(ALTERNATE_OP_DIR, ignore_errors=True)
    print(f"Removed {ALTERNATE_OP_DIR}")

    # /data/openpilot is deleted by the installer

    # Delete /data/continue.sh to trigger an installer without a reset
    if self.is_agnos:
      if os.path.exists(self.CONTINUE_FILE):
        os.remove(self.CONTINUE_FILE)
    print(f"Removed {self.CONTINUE_FILE}")

    sys.exit(0)

  def retry_action(self):
    print("Retry button pressed")
    key = KeyFileManager().installed_key
    if key:
      question = f"Key installed: {key}\n\n"
    else:
      question = "!!!! Key not installed.\n\n"
    question += "Reboot without changing anything?"
    should_reboot = YesNoDialog.ask(question)
    if not should_reboot:
      print("Action cancelled")
      return
    print("Action confirmed")

    # Do nothing
    sys.exit(0)
