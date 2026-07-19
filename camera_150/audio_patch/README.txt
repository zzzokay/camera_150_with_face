针对仓库：zzzokay/camera_150_with_face（当前 main 分支）

文件：
- apply_audio_chain.py：自动修改网络推流、本地录制、一键启动，并创建 audio_chain.py 与 AUDIO_CHAIN.md。
- audio_chain.py：新增模块的单独副本，便于查看。

使用：
1. 把 audio_patch 目录复制到仓库根目录。
2. 先检查：
   python3 audio_patch/apply_audio_chain.py --check
3. 正式应用：
   python3 audio_patch/apply_audio_chain.py
4. 按脚本输出运行 py_compile。
5. 按 camera_150/AUDIO_CHAIN.md 进行板端验证。

脚本会为三个被修改的文件各保存一个 .before_audio_chain 备份。
