<div align="center" style="text-align: center;">
<h1>openpilot-pc</h1>
<b>在pc设备上运行sunnypilot </b>
</div>

* PC最好有GPU可以支持opencl的加速

## 安装教程
安装教程文档：https://gitee.com/huheas/pilotosinit

## 数据分析
参考 [juggler数据分析](tools/plotjuggler/README.md)

## Secoc
secoc 参考文档：https://github.com/I-CAN-hack/secoc

为需要使用secoc获取解密的车型内置了secoc key脚本
  1. 首先启动汽车进入Not Ready To Drive(慢慢按两次启动键，不需要踩制动踏板，POWER)
  2. 先关闭openpilot程序，linux终端进入项目目录下
  3. 运行python key.py
  4. 如果报错类似：Unexpected application version! b'\x018965B4221000\x00\x00\x00\x00'，请把b''引号里面的值复制到项目key.py脚本中的APPLICATION_VERSIONS中，例如下方代码
  5. 最后看到SecOCKey输出则说明成功，SecOCKey不需要单独复制保存，会自动永久存储到系统中，只要不重装系统那些这个SecOCKey会一直保存
```
APPLICATION_VERSIONS = {
    b'\x018965B4209000\x00\x00\x00\x00': b'\x01!!!!!!!!!!!!!!!!', # 2021 RAV4 Prime
    b'\x018965B4233100\x00\x00\x00\x00': b'\x01!!!!!!!!!!!!!!!!', # 2023 RAV4 Prime
    b'\x018965B4509100\x00\x00\x00\x00': b'\x01!!!!!!!!!!!!!!!!', # 2021 Sienna
    b'\x018965B4221000\x00\x00\x00\x00': b'\x01!!!!!!!!!!!!!!!!', # 2021 RAV4 Prime
}
```
------

![](https://user-images.githubusercontent.com/47793918/233812617-beab2e71-57b9-479e-8bff-c3931347ca40.png)

## 🌞 What is sunnypilot?
[sunnypilot](https://github.com/sunnyhaibin/sunnypilot) is a fork of comma.ai's openpilot, an open source driver assistance system. sunnypilot offers the user a unique driving experience for over 300+ supported car makes and models with modified behaviors of driving assist engagements. sunnypilot complies with comma.ai's safety rules as accurately as possible.

## 💭 Join our Discord
Join the official sunnypilot Discord server to stay up to date with all the latest features and be a part of shaping the future of sunnypilot!
* https://discord.gg/sunnypilot

  ![](https://dcbadge.vercel.app/api/server/wRW3meAgtx?style=flat) ![Discord Shield](https://discordapp.com/api/guilds/880416502577266699/widget.png?style=shield)

## Documentation
https://docs.sunnypilot.ai/ is your one stop shop for everything from features to installation to FAQ about the sunnypilot

## 🚘 Running on a dedicated device in a car
* A supported device to run this software
    * a [comma three](https://comma.ai/shop/products/three) or a [C3X](https://comma.ai/shop/comma-3x)
* This software
* One of [the 300+ supported cars](https://github.com/commaai/openpilot/blob/master/docs/CARS.md). We support Honda, Toyota, Hyundai, Nissan, Kia, Chrysler, Lexus, Acura, Audi, VW, Ford and more. If your car is not supported but has adaptive cruise control and lane-keeping assist, it's likely able to run sunnypilot.
* A [car harness](https://comma.ai/shop/products/car-harness) to connect to your car

Detailed instructions for [how to mount the device in a car](https://comma.ai/setup).

## Installation
Please refer to [Recommended Branches](#-recommended-branches) to find your preferred/supported branch. This guide will assume you want to install the latest `release-c3` branch.

* sunnypilot not installed or you installed a version before 0.8.17?
  1. [Factory reset/uninstall](https://github.com/commaai/openpilot/wiki/FAQ#how-can-i-reset-the-device) the previous software if you have another software/fork installed.
  2. After factory reset/uninstall and upon reboot, select `Custom Software` when given the option.
  3. Input the installation URL per [Recommended Branches](#-recommended-branches). Example: ```release-c3.sunnypilot.ai```.
  4. Complete the rest of the installation following the onscreen instructions.

* sunnypilot already installed and you installed a version after 0.8.17?
  1. On the comma three, go to `Settings` ▶️ `Software`.
  2. At the `Download` option, press `CHECK`. This will fetch the list of latest branches from sunnypilot.
  3. At the `Target Branch` option, press `SELECT` to open the Target Branch selector.
  4. Scroll to select the desired branch per  Recommended Branches (see below). Example: `release-c3`

|    Branch    |         Installation URL         |
|:------------:|:--------------------------------:|
| `release-c3` | https://release-c3.sunnypilot.ai |
| `staging-c3` | https://staging-c3.sunnypilot.ai |
|   `dev-c3`   | https://dev-c3.sunnypilot.ai     |

### If you want to use our newest branches (our rewrite)
> [!TIP]
>You can see the rewrite state on our [rewrite project board](https://github.com/orgs/sunnypilot/projects/2), and to install the new branches, you can use the following links


> [!IMPORTANT]
> It is recommended to [re-flash AGNOS](https://flash.comma.ai/) if you intend to downgrade from the new branches.
> You can still restore the latest sunnylink backup made on the old branches.

|      Branch      |                 Installation URL              |
|:----------------:|:---------------------------------------------:|
| `staging-c3-new` | `https://staging-c3-new.sunnypilot.ai`        |
|   `dev-c3-new`   | `https://dev-c3-new.sunnypilot.ai`            |
| `custom-branch`  | `https://install.sunnypilot.ai/{branch_name}` |
| `release-c3-new` |            **Not yet available**.             |

> [!TIP]
> Do you require further assistance with software installation? Join the [sunnypilot Discord server](https://discord.sunnypilot.com) and message us in the `#installation-help` channel.

## 🎆 Pull Requests
We welcome both pull requests and issues on GitHub. Bug fixes are encouraged.

Pull requests should be against the most current `master-new` branch.

## 📊 User Data

By default, sunnypilot uploads the driving data to comma servers. You can also access your data through [comma connect](https://connect.comma.ai/).

sunnypilot is open source software. The user is free to disable data collection if they wish to do so.

sunnypilot logs the road-facing camera, CAN, GPS, IMU, magnetometer, thermal sensors, crashes, and operating system logs.
The driver-facing camera is only logged if you explicitly opt-in in settings. The microphone is not recorded.

By using this software, you understand that use of this software or its related services will generate certain types of user data, which may be logged and stored at the sole discretion of comma. By accepting this agreement, you grant an irrevocable, perpetual, worldwide right to comma for the use of this data.

## Licensing

sunnypilot is released under the [MIT License](LICENSE). This repository includes original work as well as significant portions of code derived from [openpilot by comma.ai](https://github.com/commaai/openpilot), which is also released under the MIT license with additional disclaimers.

The original openpilot license notice, including comma.ai’s indemnification and alpha software disclaimer, is reproduced below as required:

> openpilot is released under the MIT license. Some parts of the software are released under other licenses as specified.
>
> Any user of this software shall indemnify and hold harmless Comma.ai, Inc. and its directors, officers, employees, agents, stockholders, affiliates, subcontractors and customers from and against all allegations, claims, actions, suits, demands, damages, liabilities, obligations, losses, settlements, judgments, costs and expenses (including without limitation attorneys’ fees and costs) which arise out of, relate to or result from any use of this software by user.
>
> **THIS IS ALPHA QUALITY SOFTWARE FOR RESEARCH PURPOSES ONLY. THIS IS NOT A PRODUCT.
> YOU ARE RESPONSIBLE FOR COMPLYING WITH LOCAL LAWS AND REGULATIONS.
> NO WARRANTY EXPRESSED OR IMPLIED.**

For full license terms, please see the [`LICENSE`](LICENSE) file.

## 💰 Support sunnypilot
If you find any of the features useful, consider becoming a [sponsor on GitHub](https://github.com/sponsors/sunnyhaibin) to support future feature development and improvements.


By becoming a sponsor, you will gain access to exclusive content, early access to new features, and the opportunity to directly influence the project's development.


<h3>GitHub Sponsor</h3>

<a href="https://github.com/sponsors/sunnyhaibin">
  <img src="https://user-images.githubusercontent.com/47793918/244135584-9800acbd-69fd-4b2b-bec9-e5fa2d85c817.png" alt="Become a Sponsor" width="300" style="max-width: 100%; height: auto;">
</a>
<br>

<h3>PayPal</h3>

<a href="https://paypal.me/sunnyhaibin0850" target="_blank">
<img src="https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif" alt="PayPal this" title="PayPal - The safer, easier way to pay online!" border="0" />
</a>
<br></br>

Your continuous love and support are greatly appreciated! Enjoy 🥰

<span>-</span> Jason, Founder of sunnypilot
