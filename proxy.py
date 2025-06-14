from flask import Flask, request, Response
import cloudscraper

app = Flask(__name__)
scraper = cloudscraper.create_scraper()
TARGET_DOMAIN = "https://4gtvmobile-mozai.4gtv.tv"

@app.route('/', defaults={'path': ''}, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@app.route('/<path:path>', methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def proxy(path):
    target_url = f"{TARGET_DOMAIN}/{path}"

    # 模拟真实 App 请求头
    headers = {
        "User-Agent": "%E5%9B%9B%E5%AD%A3%E7%B7%9A%E4%B8%8A/4 CFNetwork/3826.500.131 Darwin/24.5.0",
        "Referer": "https://www.4gtv.tv/",
        "fsdevice": "iOS",
        "fsversion": "3.2.8",
        "Content-Type": "application/json; charset=UTF-8",
        "Accept-Encoding": "identity"  # ❌ 禁止压缩
    }

    method = request.method
    data = request.get_data() if method in ['POST', 'PUT', 'PATCH'] else None
    params = request.args

    try:
        resp = scraper.request(
            method=method,
            url=target_url,
            headers=headers,
            data=data,
            params=params,
            cookies=request.cookies,
            stream=True,
            allow_redirects=False,
        )

        # 过滤掉一些不适合返回的响应头
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        response_headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in excluded_headers]

        return Response(
            response=resp.content,
            status=resp.status_code,
            headers=dict(response_headers),
            content_type=resp.headers.get('Content-Type', 'application/octet-stream')
        )

    except Exception as e:
        return f"❌ Proxy Error: {str(e)}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=18080)
