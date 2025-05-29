# tsk/tools_menu/actions.py
import traceback

from tsk.common.env import RECOMMENDED_OP_BRANCH, RECOMMENDED_OP_USER
from tsk.common.env import is_cache_dir_new, is_in_car
from tsk.common.key_file_manager import KeyFileManager
from tsk.tools_menu.extractor import NotAGNOSError, BoarddNotRunningError, RetryError, TSKExtractor
from tsk.ui.dialog import OkayDialog
from tsk.ui.dialog import YesNoDialog


def tsk_extractor_action():
  """Action to perform when the TSK Extractor button is pressed."""
  print("TSK Extractor button pressed")

  try:
    secoc_key = TSKExtractor.hack()
    key_manager = KeyFileManager()
    key_manager.install_key(secoc_key)
    message = "Success!\n\n"
    message += "This is your key:\n"
    message += secoc_key + "\n\n"
    message += "Take a photo of this screen."
    OkayDialog.ask(message, 120)
  except NotAGNOSError as e:
    message = str(e)
    OkayDialog.ask(message, 120)
  except (BoarddNotRunningError, RetryError) as e:
    message = f"Can't talk to the car: {e}"
    OkayDialog.ask(message, 120, True)
  except Exception as e:
    e.add_note("\n!!!! Unexpected error. Please take a photo, post it on #toyota-security, and ping @calvinspark\n")
    message = traceback.format_exc()
    OkayDialog.ask(message, 50, True)


def tsk_guide_action():
  """Action to perform when the 'Tell me what to do next' button is pressed."""
  text = ""
  if KeyFileManager().installed_key:
    text += "Security key is installed.\n\n"
    text += "If you are selling your device, run TSK Uninstaller.\n\n"
    text += f"Otherwise, go to the Reboot Menu and install {RECOMMENDED_OP_USER}/{RECOMMENDED_OP_BRANCH}."

  else:
    if is_cache_dir_new():
      text += "Congratulations on your new comma!\n\n"
    else:
      text += "Security key is not installed.\n\n"

    text += "If you know your key, run TSK Keyboard to install it.\n\n"
    text += "Otherwise, "
    if not is_in_car():
      text += "go to your car and "
    text += "run TSK Extractor."

  OkayDialog.ask(text)


def tsk_uninstaller_action():
  print("TSK Uninstaller button pressed")
  should_delete = False

  key_manager = KeyFileManager()
  key = key_manager.installed_key
  if key:
    question = f"Key installed: {key}\n\n" \
               "Uninstall?"
    should_delete = YesNoDialog.ask(question)
  else:
    nope = "Key not installed.\n\n" \
           "Nothing to do."
    OkayDialog.ask(nope)

  if not should_delete:
    print("Not deleting keys")
    return

  key_manager.uninstall_key()

