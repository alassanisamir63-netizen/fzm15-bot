import requests, time, pytz
from datetime import datetime, timezone
import pandas as pd
import numpy as np

TOKEN = 8852964175:AAGz3mGv6STjtqURNZ-WJnEHxJ0XDncTlhk
CHAT_ID = "1003506265"
PAIRS = ["EURUSD=X", "GBPUSD=X"]
TF_LIST = ["5m", "15m"]

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True})

def get_yahoo_data(symbol, interval):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval={interval}"
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    data = r.json()['chart']['result'][0]
    ts = data['timestamp']
    q = data['indicators']['quote'][0]
    df = pd.DataFrame(q, index=pd.to_datetime(ts, unit='s', utc=True))
    return df.dropna()

def calc_atr14(df):
    h, l, c = df['high'], df['low'], df['close']
    tr = np.maximum(h - l, np.maximum(abs(h - c.shift()), abs(l - c.shift())))
    return tr.rolling(14).mean()

def in_session(dt_utc):
    if dt_utc.weekday() >= 5: return False
    return 7 <= dt_utc.hour < 16

def check_flip_zone(df):
    if len(df) < 20: return None, None, None, None
    df['atr'] = calc_atr14(df)
    df = df.dropna()
    
    block_high = block_low = block_active = None
    block_low_prev = None
    
    for i in range(1, len(df)):
        r, p = df.iloc[i], df.iloc[i-1]
        dt_utc = df.index[i].to_pydatetime().replace(tzinfo=timezone.utc)
        session = in_session(dt_utc)
        
        is_pause = (abs(r['close'] - r['open']) < 0.5 * r['atr']) and ((r['high'] - r['low']) > r['atr'])
        is_impulse = (abs(p['close'] - p['open']) > 1.5 * p['atr'])
        
        if is_pause and is_impulse and session:
            block_high, block_low, block_active = r['high'], r['low'], True
        
        if i == len(df)-1 and block_active and session:
            price_in_block = r['high'] >= block_low and r['low'] <= block_high
            cross_up = r['close'] > block_low and p['close'] <= block_low_prev
            
            if price_in_block and cross_up:
                heure_benin = dt_utc.astimezone(pytz.timezone('Africa/Porto-Novo')).strftime('%H:%M')
                return heure_benin, block_high, block_low, r['close']
        
        if block_active: block_low_prev = block_low
    
    return None, block_high, block_low, None

def main():
    send_telegram("🤖 <b>FZM15_Bot v7 ACTIF</b>\nM5+M15 EURUSD/GBPUSD\nSession: 08h-17h Bénin\nStrat: Flip Zone Pine v6")
    last_signal = {}
    
    while True:
        now_utc = datetime.now(timezone.utc)
        if not in_session(now_utc):
            time.sleep(60)
            continue
            
        for pair in PAIRS:
            for tf in TF_LIST:
                try:
                    df = get_yahoo_data(pair, tf)
                    sig_time, b_h, b_l, entry = check_flip_zone(df)
                    
                    key = f"{pair}_{tf}"
                    if sig_time and last_signal.get(key) != sig_time:
                        last_signal[key] = sig_time
                        name = pair.replace("=X", "")
                        tf_txt = "M5" if tf == "5m" else "M15"
                        msg = f"🚨 <b>SHORT {name} {tf_txt}</b>\n" \
                              f"Entrée: <code>{entry:.5f}</code>\n" \
                              f"Zone: H {b_h:.5f} L {b_l:.5f}\n" \
                              f"Heure: {sig_time} Bénin"
                        send_telegram(msg)
                except: pass
        time.sleep(30)

if __name__ == "__main__":
    main()
