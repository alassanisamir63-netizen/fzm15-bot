import yfinance as yf
import requests
import time
import pandas as pd
import numpy as np
from datetime import datetime, timezone, time as dt_time
import sys

# === CONFIG ===
TOKEN = "8852964175:AAGz3mGv6STjtqURNZ-WJnEHxJ0XDncTlhk"
CHAT_ID = "1003506265"
SYMBOLS = ["EURUSD", "GBPUSD"]
TIMEFRAMES = ["5m", "15m"]  # M5 et M15
# ==============

print("=== FLIP ZONE BOT START ===", flush=True)
sys.stdout.flush()

# Stockage des zones actives par symbole/timeframe
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
    """Vérifie si bougie dans session 07:00-16:00 UTC lun-ven"""
    if dt.weekday() >= 5:  # samedi=5, dimanche=6
        return False
    t = dt.time()
    return dt_time(7, 0) <= t < dt_time(16, 0)

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    atr = true_range.rolling(period).mean()
    return atr

def check_flip_zone(df):
    """Retourne zone active ou None, et détecte nouveau signal"""
    if len(df) < 20:
        return None, False
    
    df = df.copy()
    df['ATR'] = calculate_atr(df)
    df['body'] = np.abs(df['Close'] - df['Open'])
    df['range'] = df['High'] - df['Low']
    
    # Vérifie création zone sur dernière bougie fermée
    last = df.iloc[-2]  # bougie précédente (fermée)
    prev = df.iloc[-3]  # impulsion
    
    # Conditions zone
    pause_body_ok = last['body'] < 0.5 * last['ATR']
    pause_range_ok = last['range'] > 1.0 * last['ATR']
    impulse_ok = prev['body'] > 1.5 * prev['ATR']
    
    zone_created = False
    if pause_body_ok and pause_range_ok and impulse_ok:
        zone = {
            'high': last['High'],
            'low': last['Low'],
            'created_at': last.name,
            'atr': last['ATR']
        }
        zone_created = True
        return zone, False
    
    return None, False

def check_signal(df, zone):
    """Vérifie signal SHORT sur bougie fermée"""
    if zone is None or len(df) < 3:
        return False, None
    
    last = df.iloc
