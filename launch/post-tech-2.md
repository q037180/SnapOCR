# 技术长文 ②：退出码 127、消失的窗口、纯色截图

> 发 V2EX「分享创造」/ 掘金 / 知乎。语气克制，别当软文发。
> 口径与 `docs/QA-REPORT-2026-11-06.md` 第 7、8 章一致，数字都是实测。

## 标题（选一条）

1. 退出码 127、消失的窗口、纯色截图：四个「看起来没毛病」的 API
2. 给一个截图工具做深度测试，翻出 4 个会让用户以为「软件坏了」的坑
3. `QThread.wait()` 的返回值、`matchTemplate` 的纯色陷阱，和 ctypes 的句柄截断

## 正文

最近对一个 PySide6 + OpenCV 的桌面工具做了两轮深度测试。不是补单元测试，是按真实用户路径去折腾：批量处理到一半点关闭、框选时按 Alt+F4、拿纯色页面和带视频的页面做长截图、同时双击两次 exe。

翻出来的问题有个共同点：**代码看着都对，单测也都能过，但用户的现象是「软件坏了」**。记四个最典型的。

---

### 一、`QThread.wait()` 是有返回值的

现象：批量识别 5 张图，处理中点关闭窗口，进程**退出码 127**（abort，不是正常退出）。

原因在收尾函数。`wait()` 被调用了，但返回值没人接：

```python
for w in workers:
    w.wait(500)   # 返回 bool，False = 还没结束
QApplication.quit()
```

`wait(ms)` 超时返回 `False`，此时线程还在跑。主窗口析构把 QThread 对象一起销毁，Qt 对「运行中的 QThread 被析构」是直接 abort。批量 500 张、首次下载模型这些场景都远超 500 ms，必现。

改法不是把超时调大，而是**先请求收手、再共享一个 deadline 逐个等、等不完的挂 `finished` 延后退出**：

```python
deadline = time.monotonic() + 3.0   # 所有线程共享这 3 秒，别挨个叠加
still = []
for w in pending:
    left = max(0, int((deadline - time.monotonic()) * 1000))
    if not w.wait(left):
        still.append(w)
if still:
    for w in still:
        w.finished.connect(lambda w=w: self._on_quit_finished(w))
    return          # 界面提示「后台任务正在结束」，全部结束才真正 quit
QApplication.quit()
```

另外一条硬规矩：线程对象的清理走 `finished.connect(deleteLater)`，**绝不在 done 槽里直接丢引用**。修复后同样是 5 张处理中退出，**2.0 秒、退出码 0**。

---

### 二、`WA_DeleteOnClose` 之后，Python 引用还在

现象：截图遮罩弹出时按 Alt+F4 关掉，之后再点「立即截图」，**永久无响应**，只能重启程序。

原因是 Qt 和 Python 的对象生命周期不一致。遮罩设了 `WA_DeleteOnClose`，窗口一关 C++ 对象就没了，但主窗口里 `self._overlay` 这个 Python 变量还指着它。后面任何一次调用都会抛：

```
RuntimeError: wrapped C/C++ object of type CaptureOverlay has been deleted
```

更麻烦的是状态位没清：程序以为「遮罩还开着」，于是拦住所有新的截图请求。控制条（长截图那个工具条）同理，被 Alt+F4 关掉后会一直拦着截图。

改法分两层：给这两个控件补 `closeEvent`，销毁前把 `cancelled` / `cancelClicked` 信号补发出去；主窗口侧加 `_overlay_alive()` / `_longshot_alive()` 探测，所有访问都包 `try/except RuntimeError`，异常时顺手把状态清干净。**凡是持有 `WA_DeleteOnClose` 控件引用的地方，都要假设它随时可能是个空壳。**

---

### 三、`matchTemplate` 在纯色图上处处得 1.0

这个最隐蔽。长截图的做法是：每滚一帧，取新帧顶部 100 px 当模板，在累计图尾部用 `TM_CCOEFF_NORMED` 找它出现在哪，据此算重叠高度。

页面顶部恰好是大片纯色时，模板方差接近 0，相关系数**处处都是 1.0**，`minMaxLoc` 退化为 `(0, 0)` —— 被算成「这一帧整帧都已经存在」，连续 3 帧无变化就判定「滚到底了」。用户看到的是一张只截了开头的长图。周期性内容（等距代码行、表格行）同理，会出现多个等分峰值。

第一轮的补丁是**方差预检 + 像素复核**：纯色模板直接走追加兜底；模板匹配给出位置后，再用 `cv2.absdiff` 比一次真实像素，对不上就不认。

但真正难的是**页面里有视频**：占 22% 面积的固定位置噪点，会把相关系数压到 0.5 左右。若还按 0.75 卡关，每一帧都被整帧追加，长图里出现一整段重复内容（实测 2400 px，正常应为 900 px）。三处改动才解决：

1. **相关系数降级为粗筛**：阈值 0.75 → 0.35，只用来排序候选，裁决交给像素复核；
2. **模板缩 4 倍做粗搜**：随机噪点被平均掉、排版结构还在，再回全分辨率小窗口细化；顶部条压着动态内容时，还可以换中段/底部条重试；
3. **判据换成「逐列差异比例的中位数」**：对得齐时绝大多数列几乎完全一致，只有视频那几列对不上（中位数 < 0.06）；整段错位时是整体都差。比「差异像素占比」更能区分**局部动态内容**和**整帧对不上**。连续两轮都对不上的列记进 `ignore`，之后既不参与匹配也不参与复核。

结果：固定视频 2400 px（5 次 append）→ **900 px（5 次 overlap）**；视频 + 滚动条同时存在 2100 px → **900 px**。页面整段换内容、页面根本没动、整体亮度漂移这三个反例也都能正确区分，不会把「该结束」判成「继续拼」。

---

### 四、单实例保护，和 ctypes 的句柄截断

原先用 `QLocalServer` 做单实例：新进程连一下 socket，连得上就说明已有实例、请求唤起后退出。绝大多数时候没问题，但**两个进程同时启动**时，谁都还没 `listen`，互相探不到，于是双双起来 —— 两套全局键盘钩子、两份历史快照互相覆盖。

改成内核互斥体仲裁：

```python
import ctypes
k32 = ctypes.WinDLL("kernel32", use_last_error=True)   # get_last_error 依赖它
k32.CreateMutexW.restype = ctypes.c_void_p             # 关键，见下
k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
h = k32.CreateMutexW(None, False, "Local\\SnapOCR-single-instance")
already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
```

两行都不能省：

- `restype` 必须显式设成 `c_void_p`：ctypes 默认把返回值当 `c_int`，**64 位下 HANDLE 会被截断成 32 位**。这行不写，到 64 位就变成偶发的句柄失效；
- `ctypes.get_last_error()` 只在用 `WinDLL(..., use_last_error=True)` 时才取得到值，用 `ctypes.windll.kernel32` 配它会永远返回 0 —— 于是「已经有实例」永远判成 false，锁形同虚设。`QLocalServer` 降级成纯粹的「唤起已有窗口」，并提前到主窗口创建之前就开始 listen；抢锁失败的进程重试唤起 12 次，仍连不上就提示「已在运行，请从托盘打开」再退出。

非 Windows 用 `QLockFile` 兜底。实测并发启动 3 个只活 1 个，第二实例 0.80 s 退出；打包成 exe 后真实双进程复测，第二实例 878 ms 退出，只剩 1 个进程。

**外加一个短的**：`QProgressDialog.reset()` 会触发 `canceled` 信号。PDF 识别正常跑完时先 `reset()` 再 `close()`，结果被自己的「用户取消」回调判成取消。先 `canceled.disconnect()` 再 reset 就行 —— 一个把正常完成误报成取消的 bug，藏在一行看起来纯清理的代码里。

---

### 结论

这四件事没有一件是业务逻辑写反了。它们都藏在 API 契约的脚注里：`wait()` 会超时、`DeleteOnClose` 只删 C++ 那半边、相关系数在零方差输入上退化、ctypes 默认返回 `int`。共同的解法也不是加判断，而是**按用户会怎么折腾去测一遍**——退出、强关、纯色输入、并发启动，这些路径平时没人走，一走就是崩溃级现象。

---

顺带说下这个工具：SnapOCR，Windows 离线截图 OCR，按一次热键框选就取字，深色 IDE 截图自动反色增强，识别结果进本地可搜索历史。上面是给它做深度测试时的记录，完整 QA 报告、复现脚本和实测数据在 https://github.com/q037180/SnapOCR ，MIT。

## 配图（本地上传）

| 文件 | 建议位置 |
| --- | --- |
| `assets/compare-dark-ui.png` | 开头，深色界面预处理前后真实像素对比 |
| `assets/hero-15s.gif` | 第三节前后，长截图效果 |
| `assets/social-preview.png` | 需要封面时用 |

## 发布提示

- V2EX 发「分享创造」，正文别求 star、别写「重磅 / 神器」，结尾放一句仓库链接即可；自己补的第一条评论可以说明「数据是压测实测，不是估计值」。
- 掘金可拆成上下两篇：上篇一、二（Qt 生命周期），下篇三、四（图像算法与进程）。
- 评论区大概率会问「为什么不用 X 库」，提前准备好「取舍是什么」，别临时编。
