import yfinance as yf
import requests
import time
import pandas as pd
import numpy as np
from datetime import datetime, timezone, time as dt_time
import sys

print("=== FLIP ZONE BOT START ===", flush=True)
sys.stdout.flush()

# === CONFIG ===
TOKEN = "8852964175:AAGz3mGv6STjtqURNZ-WJnEHxJ0XDncTlhk"
CHAT_ID = "1003506265"
SYMBOLS = ["EURUSD", "GBPUSD"]
TIMEFRAMES = ["5m", "15m"]
# ==============

active_zones = {}

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}
        r = requests.post(url, data=data, timeout=10)
        print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] TG {r.status_code}", flush=True)
        return True
    except Exception as e:
        print(f"ERR TG: {e}", flush=True)
        return False

def in_session(dt):
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    return dt_time(7, 0) <= t < dt_time(16, 0)

def calculate_atr(df, period=14):
    try:
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr = true_range.rolling(period).mean()
        return atr
    except:
        return pd.Series([0]*len(df))

def check_flip_zone(df):
    try:
        if len(df) < 20:
            return None
        df = df.copy()
        df['ATR'] = calculate_atr(df)
        df['body'] = np.abs(df['Close'] - df['Open'])
        df['range'] = df['High'] - df['Low']
        last = df.iloc[-2]
        prev = df.iloc[-3]
        pause_body_ok = last['body'] < 0.5 * last['ATR']
        pause_range_ok = last['range'] > 1.0 * last['ATR']
        impulse_ok = prev['body'] > 1.5 * prev['ATR']
        if pause_body_ok and pause_range_ok and impulse_ok:
            zone = {
                'high': float(last['High']),
                'low': float(last['Low']),
                'created_at': last.name,
                'atr': float(last['ATR'])
            }
            return zone
    except Exception as e:
        print(f"ERR Zone: {e}", flush=True)
    return None

def check_signal(df, zone):
    try:
        if zone is None or len(df) < 3:
            return False, None
        last = df.iloc[-2]
        prev = df.iloc[-3]
        touches = last['High'] >= zone['low'] and last['Low'] <= zone['high']
        prev_below = prev['Close'] <= zone['low']
        curr_above = last['Close'] > zone['low']
        cross_up = prev_below and curr_above
        if touches and cross_up:
            return True, last
    except Exception as e:
        print(f"ERR Signal: {e}", flush=True)
    return False, None

def analyze_symbol_tf(symbol, tf):
    key = f"{symbol}_{tf}"
    try:
        period = "5d" if tf == "15m" else "2d"
        df = yf.download(f"{symbol}=X", period=period, interval=tf, progress=False, auto_adjust=False)
        if df.empty or len(df) < 20:
            return
        # FIX : gère MultiIndex de yfinance
        df.columns = [str(c[0]).capitalize() if isinstance(c, tuple) else str(c).capitalize() for c in df.columns]
        
        last_time = df.index[-2].to_pydatetime().replace(tzinfo=timezone.utc)
        if not in_session(last_time):
            return
        new_zone = check_flip_zone(df)
        if new_zone:
            active_zones[key] = new_zone
            print(f"[{symbol} {tf}] Zone: {new_zone['low']:.5f}-{new_zone['high']:.5f}", flush=True)
        if key in active_zones:
            zone = active_zones[key]
            signal, candle = check_signal(df, zone)
            if signal:
                entry = float(candle['Close'])
                atr = zone['atr']
                d = 1.5 * atr
                tp, sl = entry - d, entry + 3 * d
                be, limite = entry - d/2, entry - 0.2 * d
                renfort = entry + 2 * d
                spread = 0.00003
                msg = f"🔴 <b>FLIP ZONE {symbol} {tf.upper()}</b>\nSHORT @ {entry:.5f}\nTP: {tp:.5f} | SL: {sl:.5f}\nBE: {be:.5f} | Renfort: {renfort:.5f}\nLimite: {limite:.5f}\nATR: {atr:.5f}"
                send_telegram(msg)
                print(f"SIGNAL {symbol} {tf}", flush=True)
                del active_zones[key]
    except Exception as e:
        print(f"ERR {symbol} {tf}: {e}", flush=True)

# === DÉMARRAGE ===
try:
    send_telegram("🤖 <b>Flip Zone Bot ACTIF</b>\nM5 + M15 EURUSD/GBPUSD")
    print("Boucle lancée...", flush=True)
    while True:
        try:
            now = datetime.now(timezone.utc)
            print(f"\n--- {now.strftime('%H:%M:%S')} UTC ---", flush=True)
            for symbol in SYMBOLS:
                for tf in TIMEFRAMES:
                    analyze_symbol_tf(symbol, tf)
            time.sleep(60)
        except Exception as e:
            print(f"CRASH BOUCLE: {e}", flush=True)
            time.sleep(30)
except Exception as e:
    print(f"CRASH FATAL: {e}", flush=True)
    sys.exit(1)
