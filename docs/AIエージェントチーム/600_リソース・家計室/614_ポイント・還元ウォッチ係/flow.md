# 614 フロー（たたき）

```
[定例 launchd / 朝取りこぼし / 人依頼]
        ↓
  ┌─────┼─────┐
  ↓     ↓     ↓
テイチャン  ETC還元  Vポイント定例
--push     --push   --apply --push
  ↓     ↓     ↓
  └─────┼─────┘
        ↓
jarvis_points_rebate_slack_report.py
  --kind teiki | etc | vpoint
        ↓
Slack #report（【614｜…】）＋ reports/ 控え
  ＋ 各ダッシュ /vpoint /etc
```

失敗時は `#ops`。612（課金・年会費＝払う側）とは別線。  
FlowForge ノード化は第2段階（作り込み待ち）。
