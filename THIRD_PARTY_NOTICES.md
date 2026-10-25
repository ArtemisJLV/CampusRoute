# 第三方项目与数据

| 项目 | 用途 | 版本 | 原许可 |
| --- | --- | --- | --- |
| [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) | 可选iPhone后端：USB 设备识别、开发者服务、定位接口 | 11.36.0 | GPL-3.0-or-later |
| [packaging](https://packaging.pypa.io/) | iPhone 系统版本解析与兼容性检查 | 26.3 | Apache-2.0 OR BSD-2-Clause |
| [gpxpy](https://github.com/tkrajina/gpxpy) | GPX 文件解析 | 1.6.2 | Apache-2.0 |
| [GeographicLib for Python](https://github.com/geographiclib/geographiclib-python) | WGS84 椭球距离与路线插值 | 2.1 | MIT |
| [geojson](https://github.com/jazzband/geojson) | GeoJSON 文件读取与校验 | 3.2.0 | BSD-3-Clause |
| [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) | 终端输入编辑、状态重绘与窗口缩放 | 3.0.53 | BSD-3-Clause |
| [Leaflet](https://leafletjs.com/) | 浏览器交互地图 | 1.9.4 | BSD-2-Clause |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | 校园路线几何与在线底图 | 路线文件中记录数据日期 | ODbL-1.0 |

Python 依赖通过包管理器安装；各发行包保留自身许可。Leaflet 的本地 JavaScript、CSS、图片资源未经修改，许可原文保存在 `LICENSES/Leaflet-BSD-2-Clause.txt` 与组件目录中。项目代码使用 GPL-3.0-or-later；Leaflet 资源与路线数据分别遵循原许可。

开发检查使用 [build](https://github.com/pypa/build)、[twine](https://github.com/pypa/twine)、[Ruff](https://github.com/astral-sh/ruff)、[pyte](https://github.com/selectel/pyte) 与 [Pexpect](https://github.com/pexpect/pexpect)，通过 `dev` 可选依赖安装，各发行包保留自身许可。

## 地图数据

`src/campusroute/data/` 中同济、复旦、交大、华东师大六条预设的路线几何源自 OpenStreetMap，由 © OpenStreetMap contributors 提供，按照 [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) 发布。许可原文见 `LICENSES/ODbL-1.0.txt`。这些路线文件中的 `source_url` 指向具体地图对象，`retrieved_at` 记录数据获取日期，`geometry_note` 说明路线几何的构成。

`sufe-wudong.geojson` 来自用户提供的 `custom-route.geojson`，由用户选取足球场四角后使用CampusRoute参数化生成，按项目路线数据的ODbL-1.0许可收录。保留 `estimated`、`generator`、四角、间距、内收参数和原文件名，不将其标注为OSM跑道轮廓或现场测量数据。

在线底图来自 `https://tile.openstreetmap.org/`。地图署名在页面持续显示，瓦片请求遵循 [OpenStreetMap 瓦片使用政策](https://operations.osmfoundation.org/policies/tiles/)；程序不预取或批量下载瓦片。

## 场馆名称资料

- [同济大学体育部：体育场馆开放方案](https://sports.tongji.edu.cn/info/1049/3133.htm)：四平路一·二九田径场与嘉定校区田径场。
- [复旦大学：四校区体育场馆介绍](https://www.fudan.edu.cn/2020/0923/c24a106433/page.htm)：邯郸校区南区田径场。
- [上海交通大学：胡法光体育场翻新工程验收](https://news.sjtu.edu.cn/jdyw/20221129/177130.html)：闵行校区胡法光体育场。
- [华东师范大学：场馆服务介绍](https://www.ecnu.edu.cn/info/1094/62100.htm)：闵行校区东田径场、中北校区共青场。

学校资料用于核对场馆名称与校区归属。路线数据遵循 OpenStreetMap 的数据许可。

- [上海财经大学体育场馆介绍](https://sports.sufe.edu.cn/63/a8/c1930a222120/page.htm)：用于核对武东田径场的场馆信息，没有复制网页图片，也没有据此生成跑道坐标。程序收录的用户估算轨迹单圈约412.444米，与场馆介绍中的标准400米分开说明。

Android接收端使用Android平台API，无第三方运行库。ADB（Android SDK Platform-Tools）、JDK和Android SDK构建工具由用户独立安装，本仓库不分发这些工具。APK内包含本项目编译代码；本地调试签名不用于正式发布。
