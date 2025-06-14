import cloudscraper
import base64
import uuid
import datetime
import hashlib
import time
import json
import sys
import re
import warnings
import os
import argparse
from urllib.parse import urljoin
from Crypto.Cipher import AES

warnings.filterwarnings("ignore")

# 默认配置
DEFAULT_USER_AGENT = "%E5%9B%9B%E5%AD%A3%E7%B7%9A%E4%B8%8A/4 CFNetwork/3826.500.131 Darwin/24.5.0"
DEFAULT_TIMEOUT = 10  # seconds
CACHE_FILE = os.path.expanduser('~/.4gtvcache.txt')
CACHE_TTL = 0 * 3600  # 2小时有效期

# 默认账号（可被环境变量覆盖）
DEFAULT_USER = os.environ.get('GTV_USER', '您的4gtv的账号')
DEFAULT_PASS = os.environ.get('GTV_PASS', '您的4gtv的密码')

# 加载缓存
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            raw = json.load(f)
            CACHE = {k: (float(v[0]), v[1]) for k, v in raw.items()}
    except Exception:
        CACHE = {}
else:
    CACHE = {}


def save_cache():
    try:
        serializable = {k: [v[0], v[1]] for k, v in CACHE.items()}
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(serializable, f)
    except Exception as e:
        print(f"⚠️ 缓存保存失败: {e}")


def generate_uuid(user):
    """根据账号和当前日期生成唯一 UUID，确保不同用户每天 UUID 不同"""
    today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    name = f"{user}-{today}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name)).upper()


def generate_4gtv_auth():
    head_key = "PyPJU25iI2IQCMWq7kblwh9sGCypqsxMp4sKjJo95SK43h08ff+j1nbWliTySSB+N67BnXrYv9DfwK+ue5wWkg=="
    KEY = b"ilyB29ZdruuQjC45JhBBR7o2Z8WJ26Vg"
    IV = b"JUMxvVMmszqUTeKn"
    decoded = base64.b64decode(head_key)
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    decrypted = cipher.decrypt(decoded)
    pad_len = decrypted[-1]
    decrypted = decrypted[:-pad_len].decode('utf-8')
    today = datetime.datetime.utcnow().strftime('%Y%m%d')
    sha512 = hashlib.sha512((today + decrypted).encode()).digest()
    return base64.b64encode(sha512).decode()


def sign_in_4gtv(user, password, fsenc_key, auth_val, ua, timeout):
    url = "https://api2.4gtv.tv/AppAccount/SignIn"
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "fsenc_key": fsenc_key,
        "fsdevice": "iOS",
        "fsversion": "3.2.8",
        "4gtv_auth": auth_val,
        "User-Agent": ua
    }
    payload = {"fsUSER": user, "fsPASSWORD": password, "fsENC_KEY": fsenc_key}
    scraper = cloudscraper.create_scraper()
    scraper.headers.update({"User-Agent": ua})
    resp = scraper.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data.get("Data") if data.get("Success") else None


def get_all_channels(ua, timeout):
    url = 'https://api2.4gtv.tv/Channel/GetChannelBySetId/1/pc/L/V'
    headers = {"accept": "*/*", "origin": "https://www.4gtv.tv", "referer": "https://www.4gtv.tv/", "User-Agent": ua}
    scraper = cloudscraper.create_scraper()
    scraper.headers.update({"User-Agent": ua})
    resp = scraper.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if data.get("Success"):
        return [(ch.get("fs4GTV_ID"), str(ch.get("fnID"))) for ch in data.get("Data", [])]
    return []


def get_4gtv_channel_url(channel_id, fnCHANNEL_ID, fsVALUE, fsenc_key, auth_val, ua, timeout):
    headers = {
        "content-type": "application/json",
        "fsenc_key": fsenc_key,
        "accept": "*/*",
        "fsdevice": "iOS",
        "fsvalue": "",
        "fsversion": "3.2.8",
        "4gtv_auth": auth_val,
        "Referer": "https://www.4gtv.tv/",
        "User-Agent": ua
    }
    payload = {
        "fnCHANNEL_ID": fnCHANNEL_ID,
        "clsAPP_IDENTITY_VALIDATE_ARUS": {"fsVALUE": fsVALUE, "fsENC_KEY": fsenc_key},
        "fsASSET_ID": channel_id,
        "fsDEVICE_TYPE": "mobile"
    }
    scraper = cloudscraper.create_scraper()
    scraper.headers.update({"User-Agent": ua})
    resp = scraper.post('https://api2.4gtv.tv/App/GetChannelUrl2', headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if data.get('Success') and 'flstURLs' in data.get('Data', {}):
        return data['Data']['flstURLs'][1]
    return None


def extract_best_url(m3u8_url, ua, timeout):
    scraper = cloudscraper.create_scraper()
    scraper.headers.update({"User-Agent": ua})
    resp = scraper.get(m3u8_url, timeout=timeout)
    resp.raise_for_status()
    content = resp.text
    m = re.search(r'#EXT-X-STREAM-INF:.*?RESOLUTION=1920x1080.*?\n(.*?)\n', content, re.DOTALL)
    if m:
        return urljoin(m3u8_url, m.group(1).strip())
    streams = re.findall(r'#EXT-X-STREAM-INF:.*?RESOLUTION=(\d+x\d+).*?\n(.*?)\n', content, re.DOTALL)
    if streams:
        streams.sort(key=lambda x: int(x[0].split('x')[0]), reverse=True)
        return urljoin(m3u8_url, streams[0][1].strip())
    return None


def get_stream_url(channel_id, fnCHANNEL_ID, fsVALUE, fsenc_key, auth_val, ua, timeout, force_refresh=False):
    now = time.time()
    if not force_refresh:
        entry = CACHE.get(channel_id)
        if entry and now - entry[0] < CACHE_TTL:
            try:
                scraper = cloudscraper.create_scraper()
                scraper.headers.update({"User-Agent": ua})
                if scraper.head(entry[1], timeout=timeout).status_code == 200:
                    return entry[1]
            except:
                pass
    master = get_4gtv_channel_url(channel_id, fnCHANNEL_ID, fsVALUE, fsenc_key, auth_val, ua, timeout)
    if not master:
        return None
    final = extract_best_url(master, ua, timeout)
    if final:
        CACHE[channel_id] = (now, final)
        save_cache()
    return final


def print_cache_info():
    now = time.time()
    for cid, (ts, url) in CACHE.items():
        age = now - ts
        print(f"Channel: {cid}, URL: {url}, Cached: {int(age)}s ago")


def main():
    p = argparse.ArgumentParser(
        prog='4gtv_cli',
        description='4GTV Stream Fetcher with Cache and CLI',
        epilog='示例:\n'
               '  4gtv_cli 4gtv-4gtv003\n'
               '  4gtv_cli --list-channels\n'
               '  4gtv_cli 4gtv-4gtv004 --refresh\n'
               '  4gtv_cli 4gtv-4gtv005 --cache-info\n'
               '  4gtv_cli 4gtv-4gtv005 --ua "CustomUA" --timeout 15',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument('channel', nargs='?', help='fs4GTV_ID of the channel, e.g. 4gtv-4gtv003')
    p.add_argument('--refresh', action='store_true', help='强制绕过缓存')
    p.add_argument('--list-channels', action='store_true', help='打印可用频道 fs4GTV_ID → fnID 列表')
    p.add_argument('--cache-info', action='store_true', help='查看当前缓存状态')
    p.add_argument('--ua', help='自定义 User-Agent')
    p.add_argument('--timeout', type=int, help='请求超时时间（秒）')
    p.add_argument('--user', default=DEFAULT_USER, help='账号，默认使用脚本内置或环境变量 GTV_USER')
    p.add_argument('--password', default=DEFAULT_PASS, help='密码，默认使用脚本内置或环境变量 GTV_PASS')
    args = p.parse_args()

    ua = args.ua or DEFAULT_USER_AGENT
    timeout = args.timeout or DEFAULT_TIMEOUT

    if args.list_channels:
        for fsid, fnid in get_all_channels(ua, timeout):
            print(f"{fsid} -> {fnid}")
        return
    if args.cache_info:
        print_cache_info()
        return

    fs4gtv_id = args.channel or '4gtv-4gtv003'

    fsenc_key = generate_uuid(args.user)
    auth_val = generate_4gtv_auth()
    fsVALUE = sign_in_4gtv(args.user, args.password, fsenc_key, auth_val, ua, timeout)
    if not fsVALUE:
        print("❌ 登录失败，无法继续")
        sys.exit(1)
    channels = get_all_channels(ua, timeout)
    fnCHANNEL_ID = dict(channels).get(fs4gtv_id)
    if not fnCHANNEL_ID:
        print("❌ 无法匹配 fs4GTV_ID 对应的 fnCHANNEL_ID")
        sys.exit(1)

    url = get_stream_url(fs4gtv_id, fnCHANNEL_ID, fsVALUE, fsenc_key, auth_val, ua, timeout, force_refresh=args.refresh)
    if url:
        print(url)
    else:
        print("⚠️ 无法获取有效播放链接")

if __name__ == '__main__':
    main()
