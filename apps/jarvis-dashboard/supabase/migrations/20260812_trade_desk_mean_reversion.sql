-- 平均回帰リズム（probe → confirm → convince / 一部撤退）
update public.trade_params
set value = value || '{
  "style": "mean_reversion_scale",
  "drop_min_pct": 0.08,
  "drop_max_pct": 0.22,
  "rebound_min_signs": 2,
  "scale_fracs": [0.25, 0.35, 0.40],
  "confirm_gain_pct": 0.02,
  "convince_rsi": 50,
  "partial_exit_frac": 0.5,
  "rhythm_fail_pct": 0.03,
  "mean_target_band": 0.015,
  "rsi_buy_low": 25,
  "rsi_buy_high": 48,
  "take_profit_pct": 0.12,
  "stop_loss_pct": 0.08,
  "max_hold_days": 20
}'::jsonb,
    updated_at = now()
where id = 'strategy_v1';
