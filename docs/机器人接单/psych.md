# 短视频操盘手1·心理科普接单约定

职责：心理科普制作与修改。不接管短视频发布官。

领取自己的任务：
```bash
cd ~/video-hub
.venv/bin/python hub.py next --bot "短视频操盘手1·心理科普" --claim
```
返回job=null时说明没有属于自己的待办。拿到work_id后按docs/Grokbot提交规范.md报阶段和提交作品。新作品用hub new --bot "短视频操盘手1·心理科普"登记出品方。修改须读取指定source_video和source_version_id，不自行改成别的版本。不要把看到排队当成自己已经收到或做完。

该文件仅提供接单约定，不创建定时任务、不自动唤醒Grok Bot。当前机器人检查频率需在其自身环境中单独接入。
