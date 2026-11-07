/** AlertFadeAnimator — mirrors openpilot/system/ui/sunnypilot/lib/utils.py */

const TARGET_FPS = 20;

export class AlertFadeAnimator {
  constructor({ durationOn = 0.75, rc = 0.05, fps = TARGET_FPS } = {}) {
    this._x = 1;
    this._frame = 0;
    this._fps = fps;
    this._durationOn = durationOn;
    this._rc = rc;
  }

  update(active) {
    if (active) {
      this._frame += 1;
      if ((this._frame % this._fps) < (this._fps * this._durationOn)) {
        this._x = 1;
      } else {
        this._stepToward(0);
      }
    } else {
      this._frame = 0;
      this._stepToward(1);
    }
    return this._x;
  }

  _stepToward(target) {
    const k = 1 - Math.exp(-1 / (this._fps * this._rc));
    this._x += (target - this._x) * k;
  }

  get alpha() {
    return this._x;
  }
}

export { TARGET_FPS };
