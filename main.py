import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timezone, timedelta

# === CONFIG TELEGRAM ===
TOKEN = "8852964175:AAGz3mGv6STjtqURNZ-WJnEHxJ0XDncTlhk"
CHAT_ID = "1003506265"

# === CONFIG STRAT ===
PAIRS = ["EURUSD=X", "GBPUSD=X"]
TF_LIST = ["5m", "15m"]
UTC_START = 7   # 07h00 UTC = 08h00 Bénin
UTC_END = 16    # 16h00 UTC = 17h00 Bénin
ATR_PERIOD = 14
SPREAD = 0.00003  # 0.3 pip
PIP = 0.0001

# Stockage zones actives : { "EURUSD=X_5m": {"high": x, "low": y, "active": True}, ... }
active_zones = {}

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data, timeout=10)
    except:
        pass

def is_session(timestamp_utc):
    """Vérifie si l'HEURE D'OUVERTURE de la bougie est dans la session 07h-16h UTC lun-ven"""
    if timestamp_utc.weekday() >= 5:  # Samedi=5, Dimanche=6
        return False
    hour = timestamp_utc.hour
    return UTC_START <= hour < UTC_END

def calc_atr(df, period=14):
    """ATR14 comme Pine Script"""
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    atr = true_range.rolling(period).mean()
    return atr

def check_flip_zone(df):
    """
    Retourne zone active ou None
    Règles Pine v6 :
    1. Bougie IMPULSION N-1 : |close-open| > 1.5*ATR14
    2. Bougie PAUSE N : |close-open| < 0.5*ATR14 ET (high-low) > 1*ATR14
    3. Zone = high/low de la PAUSE
    """
    if len(df) < ATR_PERIOD + 2:
        return None
    
    atr = calc_atr(df, ATR_PERIOD)
    if pd.isna(atr.iloc[-1]):
        return None
    
    # Bougie courante = PAUSE potentielle
    pause = df.iloc[-1]
    pause_body = abs(pause['Close'] - pause['Open'])
    pause_range = pause['High'] - pause['Low']
    atr_val = atr.iloc[-1]
    
    # Bougie précédente = IMPULSION potentielle
    impulse = df.iloc[-2]
    impulse_body = abs(impulse['Close'] - impulse['Open'])
    
    # Conditions Pine v6 exactes
    is_impulse = impulse_body > 1.5 * atr_val
    is_pause = (pause_body < 0.5 * atr_val) and (pause_range > 1.0 * atr_val)
    
    if is_impulse and is_pause:
        return {
            "high": pause['High'],
            "low": pause['Low'],
            "active": True,
            "created_at": pause.name
        }
    return None

def check_signal(df, zone, prev_zone_low):
    """
    Signal SHORT selon Pine v6 :
    1. Prix touche la zone : high >= bas_zone ET low <= haut_zone
    2. Close CROISE VERS LE HAUT le bas_zone : close > bas_zone ET prev_close <= prev_bas_zone
    3. Confirmé à la CLÔTURE
    """
    if not zone or not zone["active"]:
        return False, None
    
    candle = df.iloc[-1]
    prev_close = df.iloc[-2]['Close']
    
    # Condition 1 : Touche la zone
    touch_zone = (candle['High'] >= zone['low']) and (candle['Low'] <= zone['high'])
    
    # Condition 2 : Croisement vers le haut du bas de zone
    cross_up = (candle['Close'] > zone['low']) and (prev_close <= prev_zone_low)
    
    if touch_zone and cross_up:
        return True, candle
    
    return False, None

def calc_levels(entry, atr_val):
    """Calcule TP/SL/BE/Limite/Renfort selon Pine v6"""
    d = 1.5 * atr_val  # Unité
    
    tp = entry - d
    sl = entry + 3 * d  # 4.5 * ATR total
    be = entry - d / 2
    limite = entry - 0.2 * d
    renfort = entry + 2 * d
    
    # Niveaux MT5 avec spread
    tp_mt5 = tp + SPREAD
    sl_mt5 = sl + SPREAD
    be_mt5 = entry + SPREAD
    
    return {
        "d": d,
        "tp": tp, "sl": sl, "be": be, "limite": limite, "renfort": renfort,
        "tp_mt5": tp_mt5, "sl_mt5": sl_mt5, "be_mt5": be_mt5
    }

def format_alert(pair, tf, entry, zone, atr_val, levels, timestamp_utc):
    """Format message Telegram"""
#
