<div align="center" style="text-align: center;">
<h1>openpilot-pc</h1>
<b>在pc设备上运行sunnypilot </b>
</div>

* PC最好有GPU可以支持opencl的加速
* 实测mac的m芯片速度比较快，不需要配置第二步

<h3>
1. 环境安装
</h3>

参考 [webcam安装步骤](tools/webcam/README.md)

<h3>
2. GPU支持（可选/可跳过）
</h3>
<h4>
NVIDIA
</h4>

安装驱动
参考[官方教程](https://developer.nvidia.com/cudnn-downloads?target_os=Linux&target_arch=x86_64&Distribution=Ubuntu&target_version=24.04&target_type=deb_local)

以下为官方教程精简:

```bash
# 确保安装的nvidia驱动是cuda12
sudo apt update
sudo apt install nvidia-cuda-toolkit
wget https://developer.download.nvidia.com/compute/cudnn/9.7.1/local_installers/cudnn-local-repo-ubuntu2404-9.7.1_1.0-1_amd64.deb
sudo dpkg -i cudnn-local-repo-ubuntu2404-9.7.1_1.0-1_amd64.deb
sudo cp /var/cudnn-local-repo-ubuntu2404-9.7.1/cudnn-*-keyring.gpg /usr/share/keyrings/
sudo apt-get update
sudo apt-get -y install cudnn
sudo apt-get -y install cudnn-cuda-12
```

然后`tools/op.sh build`编译,之后运行就行


<h4>
AMD
</h4>

参考官方教程

<h4>
参数修改
</h4>

将[SConscript](selfdrive/modeld/SConscript)中`GPU=1`改称`CUDA=1`或者`AMD=1`; 将[modeld.py](selfdrive/modeld/modeld.py)中`os.environ['GPU'] = '1'`改称`os.environ['CUDA'] = '1'`或者`os.environ['AMD'] = '1'`

<h3>
3. 摄像机参数设置
</h3>

首先使用一些常规软件获取摄像头的内参参数(例如GMLCCalibration),主要是内参matrix矩阵
然后分别修改[camera.py](common/transformations/camera.py)和[ui.h](selfdrive/ui/ui.h)中相应摄像头的内参参数；另外根据自己的需求更改[camera.py](tools/webcam/camera.py)中的相机参数（像素和帧率，帧率最好是20的倍数，例如20,60）

<h3>
4. 数据分析
</h3>

参考 [juggler数据分析](tools/plotjuggler/README.md)

<h3>
5. 分支管理
</h3>

|    Branch    |         explain        |
|:------------:|:--------------------------------:|
| `master-new` | 同步sunnypilot的master-new分支 |
| `master-new-pc` | PC版的稳定版本分支（PC建议使用这个） |
| `master-new-pc-dev` | PC版的开发分支（定期同步最新改动），测试通过后会合入master-new-pc |
| `master-rk3588` | 针对rk3588的分支，具体参考RKPilot仓库 |

备注：master-new-pc-dev分支兼容comma3设备（适配BYD车型/优化纵向控制）

<h3>
6. 环境变量
</h3>

|    Branch    |         explain        |
|:------------:|:--------------------------------:|
| `DRIVER_CAM=x` | 启用DM摄像头（默认不启用），并指定其设备编号x |
| `NO_IMU=1` | 不使用can的上imu信息，适用于can信号里yawRate未填值的车型 |

<h3>
7. 免责声明！！！
</h3>

本仓库只是用来知识共享；请遵守当地法律法规，所产生的一切后果与开发者无关！

------
------
------

# sunnypilot
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

Pull requests should be against the most current `master` branch.

## 📊 User Data

By default, sunnypilot uploads the driving data to comma servers. You can also access your data through [comma connect](https://connect.comma.ai/).

sunnypilot is open source software. The user is free to disable data collection if they wish to do so.

sunnypilot logs the road-facing camera, CAN, GPS, IMU, magnetometer, thermal sensors, crashes, and operating system logs.
The driver-facing camera and microphone are only logged if you explicitly opt-in in settings.

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
