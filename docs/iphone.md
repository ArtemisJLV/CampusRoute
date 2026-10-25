# iPhone 安装与维护

[返回首页](../README.md) · [使用手册](usage.md)

## 设备与环境

- macOS 或 Windows 10/11 64位；macOS 使用 Miniconda，Windows 使用 Python 3.11 或更新版本。
- iOS 17.4 或更新版本，手机开启开发者模式，解锁并信任电脑。
- 支持数据传输的 USB 线。macOS 的 Finder 必须能够识别手机；Windows 需要安装 iTunes 或“Apple 设备”应用提供设备支持。
- 首次安装依赖、准备开发者镜像与加载地图底图需要联网。开发者镜像由 pymobiledevice3 准备，须与手机系统版本兼容；macOS 可以使用现有 Xcode 安装。

Python 最低版本与已验证范围见 [首页](../README.md#开始之前)。Apple Silicon Mac 已完成手机操作验证，Intel Mac 与 Windows + iPhone 的完整真机兼容性仍需验证。

手机开发者模式入口为 **设置 → 隐私与安全性 → 开发者模式**。按照系统提示重启并确认。系统升级可能影响开发者服务兼容性。

## macOS 首次使用

1. 安装 [Miniconda](https://www.anaconda.com/docs/getting-started/miniconda/main)，按照安装说明在 Terminal 中启用 `conda`。
2. 将完整下载包解压到固定文件夹，双击 `CampusRoute.command`。
3. 出现安装菜单时选择 **1**。启动器创建 `.conda/campusroute` 环境、安装依赖并检查版本。
4. 连接并解锁手机，在控制台依次选择 **7、8、1、2**，完成路线、参数、起点与开始操作。

启动器无法执行时，在 Terminal 进入项目文件夹后执行：

```sh
chmod +x CampusRoute.command
./CampusRoute.command
```

需要手动安装时，在项目文件夹执行：

```sh
mkdir -p work/.cache/tmp
export TMPDIR="$PWD/work/.cache/tmp"
conda env create --prefix ./.conda/campusroute --file environment.yml
conda run --prefix ./.conda/campusroute python -m pip install --no-cache-dir -e '.[ios]'
./CampusRoute.command
```

## Windows 首次使用

1. 安装 Python 3.11 或更新版本，并确认终端可以运行 `python`。
2. 安装“Apple 设备”应用或 iTunes，连接并信任手机，确认电脑能够识别设备。
3. 双击 `CampusRoute.bat`。启动器创建 `.venv` 并安装 iPhone 依赖。
4. 进入控制台后依次选择 **7、8、1、2**。

指定 Python 路径时，在项目文件夹打开 PowerShell：

```powershell
./CampusRoute.ps1 -Backend ios -Python 'Python完整路径'
```

手动安装与启动：

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[ios]"
.venv\Scripts\python -m campusroute --root . --backend ios
```

## 更新与修复

下载并解压新版本后，运行其中的启动器。也可以手动拉取源码，再使用以下升级入口安装当前文件夹中的版本。

macOS：

```sh
./CampusRoute.command --upgrade
```

Windows：

```powershell
./CampusRoute.ps1 -Backend ios -Upgrade
```

`--repair`／`-Repair` 同样可用。启动器核对已安装发行包、程序与源码版本，检查设备依赖，通过后才进入控制台。macOS 启动器通过 `PYTHONPATH` 指定当前项目的 `src` 目录；环境有效时直接进入菜单，检查失败时显示具体原因，并提供安装／升级／修复选项。Windows 自动更新独立环境。

macOS 手动修复已有环境：

```sh
conda env update --prefix ./.conda/campusroute --file environment.yml
conda run --prefix ./.conda/campusroute python -m pip install --no-cache-dir -e '.[ios]'
```

环境位于项目内 `.conda/campusroute` 或 `.venv`；移动项目文件夹后需要重新创建环境。下载中断时，先根据终端错误检查网络，再次运行启动器继续安装。

## 连接与恢复

菜单 **1** 准备路线起点，**2** 开始，**3** 暂停，**5** 恢复定位并断开，**0** 恢复定位并退出。暂停、中止或达到目标时会保持当前位置，完整行为见 [使用手册](usage.md#控制菜单)。

| 现象 | 处理方法 |
| --- | --- |
| 找不到手机 | 先确认 Finder／Apple 设备应用能识别手机，检查数据线、解锁与信任授权 |
| 开发者服务或镜像准备失败 | 确认已开启开发者模式并联网，根据终端错误检查手机系统与 pymobiledevice3 的兼容性 |
| 提示环境版本不一致 | 使用上述升级／修复入口安装当前文件夹中的版本 |
| 提示项目路径过长 | 将完整项目解压到路径较短的文件夹，并按首次使用说明安装环境 |
| 退出后定位仍异常 | 重新连接并执行菜单1、5，必要时重启手机 |

关闭窗口、强制结束进程或断电可能无法完成电脑端清理。结束使用时请优先选择菜单 **0**。
